"""Cloud transcription pipeline (docs/TRANSCRIPTION_PROCESS.md §2).

    analyze → preprocess (extract, noise floor, silences, chunk plan) → transcribe chunks
    → merge onto the original timeline → hallucination filter → cleanup → speakers → save

Every step reports progress through the job's ProgressReporter. Errors propagate to the job
manager, which turns them into a `failed` / `cancelled` state. Per-chunk results are kept on disk so
a retry only re-sends the chunks that did not finish.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.features.transcription import config, media, records, storage
from app.features.transcription.chunking import (
  ChunkPlan,
  chunk_from_dict,
  map_segments_to_original,
  merge_chunk_results,
  plan_chunks,
  speech_regions,
  trimmed_seconds,
)
from app.features.transcription.cleanup import CleanupStats, RuleCleaner, apply_llm, apply_rules, filter_hallucinations
from app.features.transcription.diarization import SpeakerLabelMapper, build_speaker_map, reference_candidates
from app.features.transcription.errors import TranscriptionJobError
from app.features.transcription.progress import ProgressReporter
from app.features.transcription.segments import ensure_segment_ids, full_text
from app.features.transcription.whisper_cloud import (
  SpeechClient,
  SpeechTarget,
  resolve_diarization_target,
  resolve_speech_target,
)

logger = logging.getLogger(__name__)

PROMPT_MAX_CHARS = 800  # ~200 tokens
PLAN_VERSION = 1
LOCAL_WRITING_PROVIDERS = {"webllm", "local", "builtin", "browser"}


@dataclass
class JobOptions:
  language: Optional[str] = None
  diarize: bool = True
  num_speakers: Optional[int] = None
  vocabulary: str = ""
  cleanup: Optional[str] = None
  summarize: bool = True

  @classmethod
  def from_dict(cls, data: Optional[dict[str, Any]]) -> "JobOptions":
    data = data or {}
    known = {f for f in cls.__dataclass_fields__}
    return cls(**{k: v for k, v in data.items() if k in known})

  def to_dict(self) -> dict[str, Any]:
    return asdict(self)


@dataclass
class JobResult:
  record: dict[str, Any]
  metrics: dict[str, Any] = field(default_factory=dict)


class _StageTicker:
  """Fire-and-forget progress updates from synchronous callbacks, at most once per second."""

  def __init__(self, reporter: ProgressReporter, stage: str, message: str, span: tuple[float, float] = (0.0, 1.0)) -> None:
    self.reporter, self.stage, self.message, self.span = reporter, stage, message, span
    self._last = 0.0
    self._tasks: set[asyncio.Task[Any]] = set()

  def __call__(self, fraction: float) -> None:
    now = time.monotonic()
    if now - self._last < 1.0:
      return
    self._last = now
    low, high = self.span
    task = asyncio.get_running_loop().create_task(self._tick(low + (high - low) * fraction))
    self._tasks.add(task)
    task.add_done_callback(self._tasks.discard)

  async def _tick(self, value: float) -> None:
    # A tick scheduled just before the stage ended must not move the job back to this stage.
    if self.reporter.snapshot.get("stage") == self.stage:
      await self.reporter.update(self.stage, value, self.message)


def _first_error(group: BaseExceptionGroup) -> BaseException:
  """The most informative failure of a chunk task group (a typed error before a cancellation)."""
  flat: list[BaseException] = []
  stack: list[BaseException] = [group]
  while stack:
    exc = stack.pop(0)
    if isinstance(exc, BaseExceptionGroup):
      stack.extend(exc.exceptions)
    else:
      flat.append(exc)
  for exc in flat:
    if isinstance(exc, TranscriptionJobError):
      return exc
  for exc in flat:
    if not isinstance(exc, asyncio.CancelledError):
      return exc
  return flat[0] if flat else group


def _user_settings(user_id: Optional[str]) -> dict[str, Any]:
  from app.ai.providers.factory import get_ai_settings

  try:
    return get_ai_settings(user_id=user_id)
  except Exception as exc:
    logger.warning("Could not load AI settings for transcription: %s", exc)
    return {}


class TranscriptionPipeline:
  def __init__(self, job_id: str, user_id: Optional[str], options: JobOptions, reporter: ProgressReporter) -> None:
    self.job_id = job_id
    self.user_id = user_id
    self.options = options
    self.reporter = reporter
    self.folder = storage.get_transcription_dir(job_id)
    self.chunk_dir = storage.chunks_dir(job_id)
    self.settings = _user_settings(user_id)
    self.metrics: dict[str, Any] = {"stage_ms": {}, "retries": 0}
    self.target: Optional[SpeechTarget] = None
    self._stats_mode = "rules"
    # "auto" lets the provider detect the language; otherwise Spanish unless the job says otherwise.
    self.language: Optional[str] = None if options.language == "auto" else (options.language or "es")

  # --- helpers -------------------------------------------------------------------------------

  def _timed(self, stage: str, started: float) -> None:
    self.metrics["stage_ms"][stage] = int((time.monotonic() - started) * 1000)

  def _cleanup_mode(self) -> str:
    mode = (self.options.cleanup or self.settings.get("transcription_cleanup") or config.default_cleanup_mode()).lower()
    return mode if mode in {"off", "rules", "llm"} else "rules"

  def _extra_fillers(self) -> list[str]:
    raw = self.settings.get("transcription_fillers") or []
    if isinstance(raw, str):
      raw = [p for p in raw.replace(";", ",").split(",")]
    return [str(p).strip() for p in raw if str(p).strip()]

  def _vocabulary(self) -> str:
    parts = [self.options.vocabulary or "", self.settings.get("transcription_vocabulary") or ""]
    return ". ".join(p.strip() for p in parts if p and p.strip())[:1000]

  # --- run -----------------------------------------------------------------------------------

  async def run(self) -> JobResult:
    record = await records.get_record(self.job_id)
    if record is None:
      raise TranscriptionJobError("corrupt_media", "La transcripción ya no existe.")
    source = storage.find_media_file(self.job_id, record)
    if source is None:
      raise TranscriptionJobError("corrupt_media", "El archivo de la transcripción ya no existe en el servidor.")

    diar_target = resolve_diarization_target(self.user_id, self.options.diarize)
    self.target = diar_target or resolve_speech_target(self.user_id)
    self.reporter.snapshot["model_info"] = self.target.label
    self.metrics.update(provider=self.target.provider, model=self.target.model, diarization="openai" if diar_target else "none")

    duration, audio_wav, chunks, trimmed = await self._preprocess(source)
    self.metrics.update(audio_s=round(duration, 1), silence_trimmed_s=round(trimmed, 1), chunks=len(chunks))

    async with SpeechClient(self.target) as client:
      results, language = await self._transcribe(client, chunks, audio_wav)
      self.metrics["retries"] = client.retries

    segments = self._merge(chunks, results)
    segments, stats = await self._clean(segments, language or self.language or "es")
    record = await self._save(record, segments, stats, duration, trimmed, language)
    storage.delete_chunks(self.job_id)
    return JobResult(record=record, metrics=self.metrics)

  # --- preprocessing ---------------------------------------------------------------------------

  async def _preprocess(self, source: Path) -> tuple[float, Path, list[ChunkPlan], float]:
    started = time.monotonic()
    await self.reporter.update("preprocessing", 0.0, "Analizando el archivo…")
    audio_wav = self.folder / "audio.wav"
    if source != audio_wav:
      duration = await media.probe_duration(source)
      if duration > config.max_duration_s():
        raise TranscriptionJobError(
          "too_long",
          f"La grabación dura {duration / 3600:.1f} h; el máximo es {config.max_duration_s() / 3600:.1f} h.",
        )
      ticker = _StageTicker(self.reporter, "preprocessing", "Extrayendo la pista de audio…", (0.0, 0.7))
      await media.extract_audio(source, audio_wav, duration, ticker)
      storage.remove_original_after_extraction(self.job_id)
    duration = await media.probe_duration(audio_wav)

    plan_file = self.folder / "plan.json"
    plan = self._load_plan(plan_file)
    if plan is None:
      regions: list[tuple[float, float]] = [(0.0, duration)]
      if config.trim_silence_enabled():
        await self.reporter.update("preprocessing", 0.75, "Detectando silencios…")
        noise = await media.measure_noise_floor(audio_wav)
        threshold = media.silence_threshold_db(noise)
        silences = await media.detect_silences(audio_wav, threshold, config.min_silence_s(), duration)
        regions = speech_regions(silences, duration)
        self.metrics.update(noise_floor_db=noise, silence_threshold_db=threshold)
        if not regions:
          raise TranscriptionJobError("empty_result")
      chunks = plan_chunks(regions, config.chunk_seconds())
      plan = {
        "version": PLAN_VERSION,
        "duration": duration,
        "provider": self.target.provider if self.target else None,
        "diarize": bool(self.target and self.target.diarize),
        "chunk_s": config.chunk_seconds(),
        "regions": [list(r) for r in regions],
        "chunks": [c.to_dict() for c in chunks],
      }
      plan_file.write_text(json.dumps(plan), encoding="utf-8")
      storage.delete_chunks(self.job_id)  # results of another plan are not reusable
    chunks = self._chunks_from_plan(plan)
    regions = [(float(s), float(e)) for s, e in plan["regions"]]
    await self.reporter.update("preprocessing", 1.0, f"Audio preparado: {len(chunks)} fragmento(s).")
    self._timed("preprocessing", started)
    return duration, audio_wav, chunks, trimmed_seconds(regions, duration)

  def _load_plan(self, plan_file: Path) -> Optional[dict[str, Any]]:
    if not plan_file.exists():
      return None
    try:
      plan = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
      return None
    same = (
      plan.get("version") == PLAN_VERSION
      and plan.get("diarize") == bool(self.target and self.target.diarize)
      and plan.get("provider") == (self.target.provider if self.target else None)
      and plan.get("chunk_s") == config.chunk_seconds()
    )
    return plan if same else None

  @staticmethod
  def _chunks_from_plan(plan: dict[str, Any]) -> list[ChunkPlan]:
    raw = plan["chunks"]
    plans = [chunk_from_dict(c, float("-inf"), float("inf")) for c in raw]
    for prev, nxt in zip(plans, plans[1:]):
      boundary = (prev.end + nxt.start) / 2
      prev.own_end = boundary
      nxt.own_start = boundary
    return plans

  # --- transcription ---------------------------------------------------------------------------

  def _result_path(self, chunk: ChunkPlan) -> Path:
    return self.chunk_dir / f"chunk_{chunk.index:03d}.json"

  def _load_result(self, chunk: ChunkPlan) -> Optional[dict[str, Any]]:
    path = self._result_path(chunk)
    if not path.exists():
      return None
    try:
      return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
      return None

  def _prompt_for(self, chunk: ChunkPlan, results: dict[int, dict[str, Any]]) -> str:
    """Glossary first (up to half the budget), then the clean tail of the previous chunk."""
    vocabulary = self._vocabulary()[: PROMPT_MAX_CHARS // 2]
    previous = results.get(chunk.index - 1)
    tail = ""
    if previous:
      text = " ".join(s.get("text_raw", "") for s in previous.get("segments", []))
      tail, _ = RuleCleaner(self.language or "es", self._extra_fillers()).clean(text[-PROMPT_MAX_CHARS * 2 :])
      budget = PROMPT_MAX_CHARS - len(vocabulary) - 2
      tail = tail[-budget:] if budget > 0 else ""
    return ". ".join(p for p in (vocabulary.strip(" ."), tail.strip()) if p)

  async def _transcribe(
    self, client: SpeechClient, chunks: list[ChunkPlan], audio_wav: Path
  ) -> tuple[dict[int, dict[str, Any]], Optional[str]]:
    started = time.monotonic()
    self.chunk_dir.mkdir(parents=True, exist_ok=True)
    results: dict[int, dict[str, Any]] = {}
    for chunk in chunks:
      loaded = self._load_result(chunk)
      if loaded is not None:
        results[chunk.index] = loaded
    total = sum(c.speech_s for c in chunks)
    done = sum(c.speech_s for c in chunks if c.index in results)
    self.reporter.set_audio_work(total, done)
    await self._report_chunks(chunks, results)

    pending = [c for c in chunks if c.index not in results]
    known: list[tuple[str, Path]] = []
    assert self.target is not None
    if self.target.diarize and pending:
      first = chunks[0]
      if first.index not in results:
        results[first.index] = await self._run_chunk(client, first, audio_wav, results, [])
        pending = [c for c in pending if c.index != first.index]
      if pending:
        known = await self._reference_clips(chunks[0], results[chunks[0].index], audio_wav)

    semaphore = asyncio.Semaphore(config.chunk_concurrency(self.target.provider))

    failed = asyncio.Event()

    async def _worker(chunk: ChunkPlan) -> None:
      async with semaphore:
        # A chunk released by a failing sibling must not reach the provider before the group cancels it.
        if failed.is_set():
          return
        try:
          results[chunk.index] = await self._run_chunk(client, chunk, audio_wav, results, known)
        except BaseException:
          failed.set()
          raise

    try:
      async with asyncio.TaskGroup() as group:
        for chunk in pending:
          group.create_task(_worker(chunk))
    except BaseExceptionGroup as group_error:
      raise _first_error(group_error) from group_error

    self._timed("transcribing", started)
    language = next((r.get("language") for r in results.values() if r.get("language")), None)
    return results, language

  async def _run_chunk(
    self,
    client: SpeechClient,
    chunk: ChunkPlan,
    audio_wav: Path,
    results: dict[int, dict[str, Any]],
    known: list[tuple[str, Path]],
  ) -> dict[str, Any]:
    chunk_file = self.chunk_dir / f"chunk_{chunk.index:03d}.mp3"
    if not chunk_file.exists():
      await media.export_regions(audio_wav, chunk.regions, chunk_file)
    assert self.target is not None
    if self.target.diarize:
      result = await client.diarize(chunk_file, language=self.language, known_speakers=known)
    else:
      result = await client.transcribe(chunk_file, language=self.language, prompt=self._prompt_for(chunk, results))
    self._result_path(chunk).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    chunk_file.unlink(missing_ok=True)
    results[chunk.index] = result
    self.reporter.add_audio_done(chunk.speech_s)
    await self._report_chunks(None, results, preview=result.get("segments", [])[-1:])
    return result

  async def _report_chunks(
    self,
    chunks: Optional[list[ChunkPlan]],
    results: dict[int, dict[str, Any]],
    preview: Optional[list[dict[str, Any]]] = None,
  ) -> None:
    total = self.metrics.get("chunks") or (len(chunks) if chunks else 0)
    done = len(results)
    message = f"Transcribiendo fragmento {min(done + 1, total)} de {total}…" if done < total else "Transcripción recibida."
    await self.reporter.update(
      "transcribing",
      self.reporter.audio_fraction,
      message,
      chunks_done=done,
      chunks_total=total,
      preview=(preview[0].get("text_raw") if preview else self.reporter.snapshot.get("preview")),
    )

  async def _reference_clips(self, first: ChunkPlan, result: dict[str, Any], audio_wav: Path) -> list[tuple[str, Path]]:
    mapper = SpeakerLabelMapper()
    labelled = map_segments_to_original(first, mapper.label_segments(first.index, result.get("segments", [])))
    clips: list[tuple[str, Path]] = []
    for speaker_id, start, end in reference_candidates(labelled):
      clip = self.chunk_dir / f"ref_{speaker_id}.mp3"
      try:
        if not clip.exists():
          await media.export_clip(audio_wav, start, end, clip)
        clips.append((speaker_id, clip))
      except Exception as exc:
        logger.warning("Could not export speaker reference %s for %s: %s", speaker_id, self.job_id, exc)
    return clips

  # --- merge, clean, save ----------------------------------------------------------------------

  def _merge(self, chunks: list[ChunkPlan], results: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    assert self.target is not None
    per_chunk: dict[int, list[dict[str, Any]]] = {}
    if self.target.diarize:
      mapper = SpeakerLabelMapper()
      for chunk in chunks:
        per_chunk[chunk.index] = mapper.label_segments(chunk.index, results.get(chunk.index, {}).get("segments", []))
    else:
      for chunk in chunks:
        per_chunk[chunk.index] = [
          {**s, "speaker_id": "S1"} for s in results.get(chunk.index, {}).get("segments", [])
        ]
    segments = merge_chunk_results(chunks, per_chunk)
    for seg in segments:
      seg.pop("id", None)
    ensure_segment_ids(segments)
    return segments

  async def _clean(self, segments: list[dict[str, Any]], language: str) -> tuple[list[dict[str, Any]], CleanupStats]:
    started = time.monotonic()
    await self.reporter.update("cleaning", 0.0, "Limpiando el texto…")
    removed = 0
    if config.hallucination_filter_enabled():
      segments, removed = filter_hallucinations(segments)
    if not segments:
      raise TranscriptionJobError("empty_result")
    mode = self._cleanup_mode()
    segments, stats = apply_rules(segments, mode=mode, language=language, extra_fillers=self._extra_fillers())
    stats.hallucinations_removed = removed
    if mode == "llm":
      provider = self._llm_cleanup_provider()
      if provider is not None:
        await self.reporter.update("cleaning", 0.3, "Limpiando muletillas con IA…")
        segments = await apply_llm(segments, provider, stats)
      else:
        self.metrics["cleanup_fallback"] = "rules"
    for seg in segments:
      seg.pop("_metrics", None)
    self.metrics.update(cleanup_mode=mode, fillers_removed=stats.fillers_removed, hallucinations_removed=removed)
    await self.reporter.update("cleaning", 1.0, "Texto limpio.")
    self._timed("cleaning", started)
    self._stats_mode = mode
    return segments, stats

  def _llm_cleanup_provider(self) -> Any:
    from app.ai.providers.factory import resolve_provider

    if (self.settings.get("provider") or "").lower() in LOCAL_WRITING_PROVIDERS:
      return None
    try:
      provider = resolve_provider(user_id=self.user_id, tier="fast")
    except Exception as exc:
      logger.warning("No writing provider for LLM transcript cleanup: %s", exc)
      return None
    return None if getattr(provider, "id", "") in LOCAL_WRITING_PROVIDERS else provider

  async def _save(
    self,
    record: dict[str, Any],
    segments: list[dict[str, Any]],
    stats: CleanupStats,
    duration: float,
    trimmed: float,
    language: Optional[str],
  ) -> dict[str, Any]:
    assert self.target is not None
    started = time.monotonic()
    if self.target.diarize:
      await self.reporter.update("diarizing", 1.0, "Hablantes identificados.")
    await self.reporter.update("saving", 0.0, "Guardando la transcripción…")
    speakers = build_speaker_map(segments, record.get("speakers") if record.get("diarization") == "openai" else None)
    for seg in segments:
      seg["speaker"] = speakers.get(seg["speaker_id"], {}).get("name", "Participante 1")
      seg.setdefault("marked", False)

    def _apply(current: dict[str, Any]) -> None:
      current.update({
        "segments": segments,
        "speakers": speakers,
        "diarization": "openai" if self.target and self.target.diarize else "none",
        "language": language or self.language or "es",
        "duration_seconds": round(duration, 3),
        "text": full_text(segments),
        "cleanup": stats.to_dict(self._stats_mode),
        "silence_trimmed_s": round(trimmed, 1),
        "status": "complete",
        "model_info": self.target.label if self.target else "Whisper",
        "provider": self.target.provider if self.target else None,
        "model": self.target.model if self.target else None,
        "job_options": self.options.to_dict(),
        "source": "cloud",
        "summary_status": "pending" if self.options.summarize else "skipped",
        "summary_error": None,
        "error": None,
        "error_code": None,
        "retryable": False,
        "turn_gap_s": config.turn_gap_s(),
      })

    saved = await records.update_record(self.job_id, _apply)
    if saved is None:
      raise TranscriptionJobError("internal", "La transcripción se eliminó durante el proceso.")
    self._timed("saving", started)
    if self.target:
      self.metrics["cost_estimate"] = self.target.estimate_cost(duration - trimmed)
    return saved
