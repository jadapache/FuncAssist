"""Boundary cases of the cloud pipeline: options, plans, chunks, progress messages, cleaning and saving."""

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.features.transcription import pipeline as pl
from app.features.transcription import storage
from app.features.transcription.chunking import ChunkPlan, plan_chunks
from app.features.transcription.errors import TranscriptionJobError
from app.features.transcription.pipeline import JobOptions
from app.features.transcription.whisper_cloud import SpeechTarget


class Reporter:
  def __init__(self):
    self.snapshot = {"stage": "preprocessing"}
    self.updates, self.audio_work, self.audio_done, self.audio_fraction = [], None, [], 0.25

  async def update(self, stage, value, message, **fields):
    self.updates.append((stage, value, message, fields))
    self.snapshot = {**self.snapshot, "stage": stage, **fields}

  def set_audio_work(self, total, done):
    self.audio_work = (total, done)

  def add_audio_done(self, seconds):
    self.audio_done.append(seconds)


GROQ = SpeechTarget("groq", "k", "whisper-x")
DIARIZE = SpeechTarget("openai", "k", "diar-1", diarize=True)


@pytest.fixture
def build(tmp_path, monkeypatch):
  monkeypatch.setattr(storage, "TRANSCRIPTIONS_DIR", tmp_path / "transcriptions")
  (tmp_path / "transcriptions").mkdir()
  for name in ("TRANSCRIPTION_MAX_DURATION_S", "TRANSCRIPTION_TRIM_SILENCE", "TRANSCRIPTION_HALLUCINATION_FILTER"):
    monkeypatch.delenv(name, raising=False)

  def make(options=None, settings=None, target=GROQ):
    monkeypatch.setattr(pl, "_user_settings", lambda user_id: settings or {})
    pipeline = pl.TranscriptionPipeline("job1", "u1", options or JobOptions(), Reporter())
    pipeline.folder.mkdir(parents=True, exist_ok=True)
    pipeline.target = target
    return pipeline

  return make


# --- options and helpers --------------------------------------------------------------


@pytest.mark.parametrize("requested, language", [("auto", None), (None, "es"), ("", "es"), ("en", "en")])
def test_the_job_language_is_auto_detected_or_defaults_to_spanish(build, requested, language):
  assert build(JobOptions(language=requested)).language == language


def test_a_new_pipeline_starts_with_empty_metrics(build):
  assert build().metrics == {"stage_ms": {}, "retries": 0}


def test_the_vocabulary_joins_the_job_and_the_settings_glossaries(build):
  assert build(JobOptions(vocabulary="  uno  "), {"transcription_vocabulary": " dos "})._vocabulary() == "uno. dos"
  assert build(JobOptions(vocabulary="uno"), {})._vocabulary() == "uno"
  assert build(JobOptions(), {"transcription_vocabulary": "dos"})._vocabulary() == "dos"
  assert build(JobOptions(vocabulary="   "), {"transcription_vocabulary": None})._vocabulary() == ""
  assert build(JobOptions(vocabulary="   "), {"transcription_vocabulary": "dos"})._vocabulary() == "dos"
  assert build(JobOptions(vocabulary="uno"), {"transcription_vocabulary": "   "})._vocabulary() == "uno"
  assert len(build(JobOptions(vocabulary="x" * 2000))._vocabulary()) == 1000


def test_stage_times_are_stored_in_milliseconds(build, monkeypatch):
  pipeline = build()
  monkeypatch.setattr(pl, "time", SimpleNamespace(monotonic=lambda: 3.5))
  pipeline._timed("cleaning", 1.0)
  assert pipeline.metrics["stage_ms"]["cleaning"] == 2500


# --- the stage ticker -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_ticks_are_throttled_to_one_a_second_and_scaled_to_the_stage_span(monkeypatch):
  reporter = Reporter()
  reporter.snapshot = {"stage": "preprocessing"}
  clock = {"now": 0.5}
  monkeypatch.setattr(pl, "time", SimpleNamespace(monotonic=lambda: clock["now"]))
  ticker = pl._StageTicker(reporter, "preprocessing", "Extrayendo…", (0.2, 0.8))
  ticker(0.5)
  assert ticker._tasks == set()
  clock["now"] = 1.0
  ticker(0.5)
  clock["now"] = 1.5
  ticker(0.9)
  await asyncio.gather(*ticker._tasks)
  assert [(u[0], round(u[1], 3), u[2]) for u in reporter.updates] == [("preprocessing", 0.5, "Extrayendo…")]
  clock["now"] = 2.0
  ticker(1.0)
  await asyncio.gather(*ticker._tasks)
  assert round(reporter.updates[-1][1], 3) == 0.8


@pytest.mark.asyncio
async def test_a_late_tick_does_not_move_the_job_back_to_an_earlier_stage(monkeypatch):
  reporter = Reporter()
  reporter.snapshot = {"stage": "transcribing"}
  ticker = pl._StageTicker(reporter, "preprocessing", "m")
  await ticker._tick(0.5)
  assert reporter.updates == []


# --- plans and chunks -----------------------------------------------------------------


def _plan(pipeline, **overrides):
  plan = {"version": pl.PLAN_VERSION, "diarize": False, "provider": "groq", "chunk_s": 600.0, "regions": [[0.0, 10.0]], "chunks": [ChunkPlan(0, [(0.0, 10.0)]).to_dict()]}
  return {**plan, **overrides}


def test_a_saved_plan_is_reused_only_when_it_matches_the_job(build):
  pipeline = build()
  plan_file = pipeline.folder / "plan.json"
  assert pipeline._load_plan(plan_file) is None
  plan_file.write_text(json.dumps(_plan(pipeline)), encoding="utf-8")
  assert pipeline._load_plan(plan_file)["version"] == pl.PLAN_VERSION
  for change in ({"version": 99}, {"diarize": True}, {"provider": "openai"}, {"chunk_s": 30.0}):
    plan_file.write_text(json.dumps(_plan(pipeline, **change)), encoding="utf-8")
    assert pipeline._load_plan(plan_file) is None, change
  plan_file.write_text("{broken", encoding="utf-8")
  assert pipeline._load_plan(plan_file) is None


def test_a_plan_made_for_diarization_matches_a_diarizing_job_only(build):
  pipeline = build(target=DIARIZE)
  plan_file = pipeline.folder / "plan.json"
  plan_file.write_text(json.dumps(_plan(pipeline, diarize=True, provider="openai")), encoding="utf-8")
  assert pipeline._load_plan(plan_file) is not None
  pipeline.target = None
  plan_file.write_text(json.dumps(_plan(pipeline, provider=None)), encoding="utf-8")
  assert pipeline._load_plan(plan_file) is not None


def test_chunks_own_the_time_up_to_the_midpoint_between_neighbours():
  chunks = plan_chunks([(0.0, 10.0), (20.0, 30.0)], 5.0)
  restored = pl.TranscriptionPipeline._chunks_from_plan({"chunks": [c.to_dict() for c in chunks]})
  assert restored[0].own_start == float("-inf") and restored[-1].own_end == float("inf")
  for previous, following in zip(restored, restored[1:]):
    assert previous.own_end == following.own_start == (previous.end + following.start) / 2


# --- prompts --------------------------------------------------------------------------


def test_the_prompt_is_the_glossary_then_the_clean_tail_of_the_previous_chunk(build):
  pipeline = build(JobOptions(vocabulary="Glosario"))
  results = {0: {"segments": [{"text_raw": "eh bueno, vamos a revisar el inventario"}]}}
  assert pipeline._prompt_for(ChunkPlan(1, [(0.0, 1.0)]), results) == "Glosario. Vamos a revisar el inventario"
  assert pipeline._prompt_for(ChunkPlan(0, [(0.0, 1.0)]), results) == "Glosario"
  assert pipeline._prompt_for(ChunkPlan(1, [(0.0, 1.0)]), {}) == "Glosario"


def _long_text():
  return " ".join(f"w{i}" for i in range(400))


def test_the_glossary_takes_at_most_half_the_prompt_and_the_tail_fills_the_rest(build):
  pipeline = build(JobOptions(vocabulary="g" * 700))
  prompt = pipeline._prompt_for(ChunkPlan(1, [(0.0, 1.0)]), {0: {"segments": [{"text_raw": _long_text()}]}})
  glossary, tail = prompt.split(". ", 1)
  assert glossary == "g" * 400 and len(tail) == pl.PROMPT_MAX_CHARS - 400 - 2
  assert len(prompt) <= pl.PROMPT_MAX_CHARS


def test_a_short_glossary_leaves_more_room_for_the_tail(build):
  pipeline = build(JobOptions(vocabulary="g" * 100))
  prompt = pipeline._prompt_for(ChunkPlan(1, [(0.0, 1.0)]), {0: {"segments": [{"text_raw": _long_text()}]}})
  glossary, tail = prompt.split(". ", 1)
  assert glossary == "g" * 100 and len(tail) == pl.PROMPT_MAX_CHARS - 100 - 2


def test_the_tail_cleaner_uses_the_job_language_and_fillers(build):
  pipeline = build(JobOptions(language="en"), {"transcription_fillers": "foo; bar"})
  results = {0: {"segments": [{"text_raw": "well, foo hello there"}]}}
  assert pipeline._prompt_for(ChunkPlan(1, [(0.0, 1.0)]), results) == "Hello there"
  auto = build(JobOptions(language="auto"))
  assert auto._prompt_for(ChunkPlan(1, [(0.0, 1.0)]), {0: {"segments": [{"text_raw": "bueno, hola"}]}}) == "Hola"


# --- preprocessing --------------------------------------------------------------------


@pytest.fixture
def media_fakes(monkeypatch):
  state = SimpleNamespace(durations={}, extracted=[])

  async def probe(path):
    return state.durations[path.name]

  async def extract(source, dest, duration, ticker):
    state.extracted.append((source.name, duration))
    dest.write_bytes(b"wav")

  monkeypatch.setattr(pl.media, "probe_duration", probe)
  monkeypatch.setattr(pl.media, "extract_audio", extract)
  monkeypatch.setenv("TRANSCRIPTION_TRIM_SILENCE", "off")
  return state


@pytest.mark.asyncio
async def test_a_recording_over_the_duration_limit_is_refused_with_the_hours(build, media_fakes, monkeypatch):
  monkeypatch.setenv("TRANSCRIPTION_MAX_DURATION_S", "3600")
  pipeline = build()
  media_fakes.durations = {"media.mp3": 7200.0}
  with pytest.raises(TranscriptionJobError) as raised:
    await pipeline._preprocess(pipeline.folder / "media.mp3")
  assert raised.value.code == "too_long" and raised.value.user_message == "La grabación dura 2.0 h; el máximo es 1.0 h."
  assert media_fakes.extracted == []


@pytest.mark.asyncio
async def test_a_recording_exactly_at_the_limit_is_accepted_and_planned(build, media_fakes, monkeypatch):
  monkeypatch.setenv("TRANSCRIPTION_MAX_DURATION_S", "3600")
  pipeline = build()
  media_fakes.durations = {"media.mp3": 3600.0, "audio.wav": 3600.0}
  duration, wav, chunks, trimmed = await pipeline._preprocess(pipeline.folder / "media.mp3")
  assert (duration, wav.name, trimmed) == (3600.0, "audio.wav", 0.0) and chunks
  assert media_fakes.extracted == [("media.mp3", 3600.0)]
  assert json.loads((pipeline.folder / "plan.json").read_text(encoding="utf-8"))["duration"] == 3600.0
  assert pipeline.reporter.updates[-1][2] == f"Audio preparado: {len(chunks)} fragmento(s)."


@pytest.mark.asyncio
async def test_an_extracted_recording_is_not_extracted_again(build, media_fakes):
  pipeline = build()
  (pipeline.folder / "audio.wav").write_bytes(b"wav")
  media_fakes.durations = {"audio.wav": 90.0}
  duration, _, _, _ = await pipeline._preprocess(pipeline.folder / "audio.wav")
  assert duration == 90.0 and media_fakes.extracted == []


# --- chunks ---------------------------------------------------------------------------


class Client:
  def __init__(self, languages=None, fail=False):
    self.calls, self.languages, self.fail = [], languages or {}, fail
    self.retries = 0

  async def transcribe(self, path, *, language, prompt=""):
    self.calls.append(("transcribe", path.stem, language, prompt))
    return {"language": self.languages.get(path.stem), "segments": [{"text_raw": f"texto de {path.stem}", "start": 0.0, "end": 1.0}]}

  async def diarize(self, path, *, language, known_speakers=()):
    self.calls.append(("diarize", path.stem, tuple(name for name, _ in known_speakers)))
    return {"language": "es", "segments": [{"text_raw": f"voz de {path.stem}", "speaker": "A", "start": 0.0, "end": 1.0}]}


@pytest.fixture
def exports(monkeypatch):
  made = []

  async def export_regions(wav, regions, dest):
    made.append(dest.name)

  monkeypatch.setattr(pl.media, "export_regions", export_regions)
  return made


def _chunks(count, seconds=10.0):
  return [ChunkPlan(i, [(i * 20.0, i * 20.0 + seconds)]) for i in range(count)]


@pytest.mark.asyncio
async def test_a_chunk_is_exported_only_when_its_file_is_missing_and_its_result_is_saved(build, exports):
  pipeline = build()
  pipeline.chunk_dir.mkdir(parents=True)
  (pipeline.chunk_dir / "chunk_001.mp3").write_bytes(b"already there")
  client = Client()
  await pipeline._run_chunk(client, _chunks(2)[1], pipeline.folder / "audio.wav", {}, [])
  assert exports == []
  await pipeline._run_chunk(client, _chunks(1)[0], pipeline.folder / "audio.wav", {}, [])
  assert exports == ["chunk_000.mp3"]
  assert json.loads((pipeline.chunk_dir / "chunk_000.json").read_text(encoding="utf-8"))["segments"][0]["text_raw"] == "texto de chunk_000"


@pytest.mark.asyncio
async def test_a_chunk_result_keeps_accents_readable_and_reports_audio_progress(build, exports):
  pipeline = build()
  pipeline.chunk_dir.mkdir(parents=True)
  client = Client()

  async def accented(path, *, language, prompt=""):
    return {"language": "es", "segments": [{"text_raw": "canción uno"}, {"text_raw": "canción dos"}, {"text_raw": "canción tres"}]}

  client.transcribe = accented
  chunk = _chunks(1, seconds=7.0)[0]
  pipeline.metrics["chunks"] = 1
  results = {}
  await pipeline._run_chunk(client, chunk, pipeline.folder / "audio.wav", results, [])
  assert "canción" in (pipeline.chunk_dir / "chunk_000.json").read_text(encoding="utf-8")
  assert pipeline.reporter.audio_done == [7.0] and results[0]["language"] == "es"
  assert pipeline.reporter.updates[-1][3]["preview"] == "canción tres"
  assert not (pipeline.chunk_dir / "chunk_000.mp3").exists()


@pytest.mark.asyncio
async def test_diarizing_chunks_use_the_diarization_client_and_the_known_speakers(build, exports):
  pipeline = build(target=DIARIZE)
  pipeline.chunk_dir.mkdir(parents=True)
  client = Client()
  await pipeline._run_chunk(client, _chunks(1)[0], pipeline.folder / "audio.wav", {}, [("S1", Path("ref.mp3"))])
  assert client.calls == [("diarize", "chunk_000", ("S1",))]


@pytest.mark.asyncio
async def test_transcription_prompts_carry_the_previous_chunk_and_the_language(build, exports):
  pipeline = build(JobOptions(language="en", vocabulary="Glossary"))
  pipeline.chunk_dir.mkdir(parents=True)
  client = Client()
  previous = {0: {"segments": [{"text_raw": "hello world"}]}}
  await pipeline._run_chunk(client, _chunks(2)[1], pipeline.folder / "audio.wav", previous, [])
  assert client.calls == [("transcribe", "chunk_001", "en", "Glossary. Hello world")]


@pytest.mark.parametrize("metric_chunks, chunks, done, message", [
  (3, None, 1, "Transcribiendo fragmento 2 de 3…"),
  (3, None, 2, "Transcribiendo fragmento 3 de 3…"),
  (3, None, 3, "Transcripción recibida."),
  (None, 4, 0, "Transcribiendo fragmento 1 de 4…"),
  (None, None, 0, "Transcripción recibida."),
])
@pytest.mark.asyncio
async def test_chunk_progress_messages_count_from_one_and_end_with_the_reception(build, metric_chunks, chunks, done, message):
  pipeline = build()
  if metric_chunks:
    pipeline.metrics["chunks"] = metric_chunks
  await pipeline._report_chunks(_chunks(chunks) if chunks else None, {i: {} for i in range(done)})
  stage, value, text, fields = pipeline.reporter.updates[-1]
  assert (stage, value, text) == ("transcribing", 0.25, message) and fields["chunks_done"] == done
  assert fields["chunks_total"] == (metric_chunks or chunks or 0)


@pytest.mark.asyncio
async def test_the_preview_is_the_latest_text_or_the_one_already_shown(build):
  pipeline = build()
  pipeline.reporter.snapshot = {"stage": "transcribing", "preview": "anterior"}
  await pipeline._report_chunks(None, {}, preview=[])
  assert pipeline.reporter.updates[-1][3]["preview"] == "anterior"
  await pipeline._report_chunks(None, {}, preview=[{"text_raw": "nuevo"}])
  assert pipeline.reporter.updates[-1][3]["preview"] == "nuevo"


@pytest.mark.asyncio
async def test_finished_chunks_on_disk_are_not_sent_again(build, exports):
  pipeline = build()
  pipeline.chunk_dir.mkdir(parents=True)
  (pipeline.chunk_dir / "chunk_000.json").write_text(json.dumps({"language": "fr", "segments": []}), encoding="utf-8")
  client = Client(languages={"chunk_001": "es"})
  results, language = await pipeline._transcribe(client, _chunks(2), pipeline.folder / "audio.wav")
  assert sorted(results) == [0, 1] and [c[1] for c in client.calls] == ["chunk_001"] and language == "fr"
  assert pipeline.reporter.audio_work == (20.0, 10.0)


@pytest.mark.asyncio
async def test_without_any_language_in_the_results_none_is_returned(build, exports):
  pipeline = build()
  results, language = await pipeline._transcribe(Client(), _chunks(2), pipeline.folder / "audio.wav")
  assert language is None and sorted(results) == [0, 1]
  assert pipeline.chunk_dir.is_dir()


@pytest.mark.asyncio
async def test_diarization_runs_the_first_chunk_alone_and_shares_its_speakers_with_the_rest(build, exports, monkeypatch):
  pipeline = build(target=DIARIZE)
  client = Client()
  seen = []

  async def references(first, result, wav):
    seen.append((first.index, result["segments"][0]["text_raw"]))
    return [("S1", Path("ref.mp3"))]

  monkeypatch.setattr(pipeline, "_reference_clips", references)
  results, _ = await pipeline._transcribe(client, _chunks(3), pipeline.folder / "audio.wav")
  assert client.calls[0] == ("diarize", "chunk_000", ()) and sorted(results) == [0, 1, 2]
  assert sorted(call[1] for call in client.calls[1:]) == ["chunk_001", "chunk_002"]
  assert all(call[2] == ("S1",) for call in client.calls[1:]) and seen == [(0, "voz de chunk_000")]


@pytest.mark.asyncio
async def test_plain_transcription_never_looks_for_speaker_references(build, exports, monkeypatch):
  pipeline = build()

  async def references(*args):
    raise AssertionError("no references without diarization")

  monkeypatch.setattr(pipeline, "_reference_clips", references)
  results, _ = await pipeline._transcribe(Client(), _chunks(3), pipeline.folder / "audio.wav")
  assert sorted(results) == [0, 1, 2]


@pytest.mark.asyncio
async def test_diarization_resumes_without_repeating_a_finished_first_chunk(build, exports, monkeypatch):
  pipeline = build(target=DIARIZE)
  pipeline.chunk_dir.mkdir(parents=True)
  (pipeline.chunk_dir / "chunk_000.json").write_text(json.dumps({"language": "es", "segments": [{"text_raw": "ya", "speaker": "A"}]}), encoding="utf-8")
  client = Client()

  async def references(first, result, wav):
    return [("S1", Path("ref.mp3"))]

  monkeypatch.setattr(pipeline, "_reference_clips", references)
  results, _ = await pipeline._transcribe(client, _chunks(2), pipeline.folder / "audio.wav")
  assert [c[1] for c in client.calls] == ["chunk_001"] and sorted(results) == [0, 1]


# --- cleaning -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleaning_counts_no_hallucinations_when_the_filter_is_off(build, monkeypatch):
  monkeypatch.setenv("TRANSCRIPTION_HALLUCINATION_FILTER", "0")
  pipeline = build()
  segments = [{"id": "s1", "text_raw": "Gracias por ver el video", "start": 0, "end": 1, "speaker_id": "S1", "_metrics": {"x": 1}}]
  cleaned, stats = await pipeline._clean(segments, "es")
  assert stats.hallucinations_removed == 0 and pipeline.metrics["hallucinations_removed"] == 0
  assert len(cleaned) == 1 and "_metrics" not in cleaned[0] and pipeline.metrics["cleanup_mode"] == "rules"


@pytest.mark.asyncio
async def test_cleaning_everything_away_is_an_empty_result(build):
  pipeline = build()
  with pytest.raises(TranscriptionJobError) as raised:
    await pipeline._clean([{"id": "s1", "text_raw": "Gracias por ver el video", "speaker_id": "S1"}], "es")
  assert raised.value.code == "empty_result"


@pytest.mark.asyncio
async def test_llm_cleanup_falls_back_to_rules_without_a_writing_provider(build, monkeypatch):
  pipeline = build(JobOptions(cleanup="llm"))
  monkeypatch.setattr(pipeline, "_llm_cleanup_provider", lambda: None)
  await pipeline._clean([{"id": "s1", "text_raw": "hola mundo", "speaker_id": "S1"}], "es")
  assert pipeline.metrics["cleanup_fallback"] == "rules" and pipeline.metrics["cleanup_mode"] == "llm"
  assert pipeline._stats_mode == "llm"


@pytest.mark.asyncio
async def test_llm_cleanup_runs_the_provider_pass(build, monkeypatch):
  pipeline = build(JobOptions(cleanup="llm"))
  seen = []

  async def apply_llm(segments, provider, stats):
    seen.append(provider)
    stats.llm_segments = 1
    return segments

  monkeypatch.setattr(pipeline, "_llm_cleanup_provider", lambda: "provider")
  monkeypatch.setattr(pl, "apply_llm", apply_llm)
  _, stats = await pipeline._clean([{"id": "s1", "text_raw": "hola mundo", "speaker_id": "S1"}], "es")
  assert seen == ["provider"] and stats.llm_segments == 1 and "cleanup_fallback" not in pipeline.metrics
  assert pipeline.reporter.updates[1][2] == "Limpiando muletillas con IA…"


# --- saving ---------------------------------------------------------------------------


@pytest.fixture
def saved(monkeypatch):
  state = SimpleNamespace(fields=None, result="record")

  async def update_record(job_id, mutate):
    record = {"id": job_id}
    mutate(record)
    state.fields = record
    return record if state.result == "record" else None

  monkeypatch.setattr(pl.records, "update_record", update_record)
  return state


def _segments():
  return [{"id": "s1", "text": "hola", "speaker_id": "S1"}, {"id": "s2", "text": "adiós", "speaker_id": "S2", "marked": True}]


@pytest.mark.asyncio
async def test_a_saved_job_records_its_outcome_and_cost(build, saved):
  pipeline = build(JobOptions(summarize=False))
  stats = pl.CleanupStats(fillers_removed=2)
  record = await pipeline._save({"id": "job1"}, _segments(), stats, 120.0, 60.04, "en")
  assert (saved.fields["language"], saved.fields["duration_seconds"], saved.fields["silence_trimmed_s"]) == ("en", 120.0, 60.0)
  await pipeline._save({"id": "job1"}, _segments(), stats, 120.0, 60.26, "en")
  assert saved.fields["silence_trimmed_s"] == 60.3
  assert (saved.fields["status"], saved.fields["source"], saved.fields["retryable"], saved.fields["summary_status"]) == ("complete", "cloud", False, "skipped")
  assert (saved.fields["provider"], saved.fields["model"], saved.fields["diarization"], saved.fields["model_info"]) == ("groq", "whisper-x", "none", GROQ.label)
  assert (saved.fields["error"], saved.fields["error_code"], saved.fields["summary_error"]) == (None, None, None)
  assert saved.fields["text"] == "hola adiós" and saved.fields["cleanup"]["fillers_removed"] == 2
  assert [s["marked"] for s in record["segments"]] == [False, True]
  assert pipeline.metrics["cost_estimate"] == round((120.0 - 60.26) / 60.0 * 0.00185, 5)
  assert pipeline.reporter.updates[-1][2] == "Guardando la transcripción…"


@pytest.mark.asyncio
async def test_the_saved_language_falls_back_to_the_job_then_spanish(build, saved):
  pipeline = build(JobOptions(language="en"))
  await pipeline._save({}, _segments(), pl.CleanupStats(), 1.0, 0.0, None)
  assert saved.fields["language"] == "en"
  auto = build(JobOptions(language="auto"))
  await auto._save({}, _segments(), pl.CleanupStats(), 1.0, 0.0, None)
  assert saved.fields["language"] == "es"


@pytest.mark.asyncio
async def test_a_diarized_save_names_the_speakers_and_marks_the_stage(build, saved):
  pipeline = build(JobOptions(summarize=True), target=DIARIZE)
  record = {"id": "job1", "diarization": "openai", "speakers": {"S1": {"name": "Ana", "color_index": 0}}}
  await pipeline._save(record, _segments(), pl.CleanupStats(), 10.0, 0.0, "es")
  assert saved.fields["diarization"] == "openai" and saved.fields["summary_status"] == "pending"
  assert saved.fields["speakers"]["S1"]["name"] == "Ana"
  assert [s["speaker"] for s in saved.fields["segments"]][0] == "Ana"
  assert pipeline.reporter.updates[0][:3] == ("diarizing", 1.0, "Hablantes identificados.")


@pytest.mark.asyncio
async def test_speakers_of_a_non_diarized_record_are_not_reused(build, saved):
  pipeline = build()
  record = {"id": "job1", "diarization": "none", "speakers": {"S1": {"name": "Ana", "color_index": 0}}}
  await pipeline._save(record, _segments(), pl.CleanupStats(), 10.0, 0.0, "es")
  assert saved.fields["speakers"]["S1"]["name"] != "Ana"


@pytest.mark.asyncio
async def test_a_record_deleted_during_the_job_is_an_internal_error(build, saved):
  saved.result = None
  with pytest.raises(TranscriptionJobError) as raised:
    await build()._save({}, _segments(), pl.CleanupStats(), 1.0, 0.0, "es")
  assert raised.value.code == "internal"


# --- the whole run --------------------------------------------------------------------


class FakeClientContext:
  def __init__(self, target):
    self.retries = 2

  async def __aenter__(self):
    return self

  async def __aexit__(self, *exc):
    return None


@pytest.fixture
def run_env(build, monkeypatch, tmp_path):
  state = SimpleNamespace(clean_language=None, save_language=None, deleted=[], diar=None, record={"id": "job1"}, media=Path("x.mp3"))

  async def get_record(job_id):
    return state.record

  async def preprocess(source):
    return 12.34, Path("audio.wav"), [ChunkPlan(0, [(0.0, 10.0)]), ChunkPlan(1, [(20.0, 30.0)])], 1.26

  async def clean(segments, language):
    state.clean_language = language
    return segments, pl.CleanupStats()

  async def save(record, segments, stats, duration, trimmed, language):
    state.save_language = language
    return {"id": "job1"}

  monkeypatch.setattr(pl.records, "get_record", get_record)
  monkeypatch.setattr(pl.storage, "find_media_file", lambda job_id, record: state.media)
  monkeypatch.setattr(pl, "resolve_diarization_target", lambda user_id, wanted: state.diar)
  monkeypatch.setattr(pl, "resolve_speech_target", lambda user_id: GROQ)
  monkeypatch.setattr(pl, "SpeechClient", FakeClientContext)
  monkeypatch.setattr(pl.storage, "delete_chunks", lambda job_id: state.deleted.append(job_id))

  def make(options=None, language=None):
    pipeline = build(options)
    pipeline.target = None

    async def transcribe(client, chunks, wav):
      return {0: {}}, language

    monkeypatch.setattr(pipeline, "_preprocess", preprocess)
    monkeypatch.setattr(pipeline, "_transcribe", transcribe)
    monkeypatch.setattr(pipeline, "_merge", lambda chunks, results: [{"id": "s1"}])
    monkeypatch.setattr(pipeline, "_clean", clean)
    monkeypatch.setattr(pipeline, "_save", save)
    return pipeline

  state.make = make
  return state


@pytest.mark.asyncio
async def test_a_run_reports_what_it_measured_and_removes_the_chunks(run_env):
  pipeline = run_env.make()
  result = await pipeline.run()
  assert result.record == {"id": "job1"} and run_env.deleted == ["job1"]
  assert pipeline.metrics["audio_s"] == 12.3 and pipeline.metrics["silence_trimmed_s"] == 1.3
  assert (pipeline.metrics["chunks"], pipeline.metrics["retries"], pipeline.metrics["provider"]) == (2, 2, "groq")
  assert (pipeline.metrics["model"], pipeline.metrics["diarization"]) == ("whisper-x", "none")
  assert pipeline.reporter.snapshot["model_info"] == GROQ.label


@pytest.mark.asyncio
async def test_a_run_with_diarization_reports_it(run_env):
  run_env.diar = DIARIZE
  pipeline = run_env.make()
  await pipeline.run()
  assert pipeline.metrics["diarization"] == "openai" and pipeline.metrics["provider"] == "openai"


@pytest.mark.parametrize("option, detected, expected", [("en", None, "en"), ("auto", None, "es"), (None, None, "es"), ("en", "fr", "fr")])
@pytest.mark.asyncio
async def test_a_run_uses_the_detected_language_then_the_job_language_then_spanish(run_env, option, detected, expected):
  pipeline = run_env.make(JobOptions(language=option), language=detected)
  await pipeline.run()
  assert run_env.clean_language == expected
  assert run_env.save_language == detected


@pytest.mark.asyncio
async def test_a_run_needs_its_record_and_its_media(run_env):
  run_env.record = None
  with pytest.raises(TranscriptionJobError) as missing:
    await run_env.make().run()
  assert missing.value.code == "corrupt_media" and missing.value.user_message == "La transcripción ya no existe."
  run_env.record = {"id": "job1"}
  run_env.media = None
  with pytest.raises(TranscriptionJobError) as no_media:
    await run_env.make().run()
  assert no_media.value.user_message == "El archivo de la transcripción ya no existe en el servidor."


# --- failures of a chunk group --------------------------------------------------------


def test_the_most_informative_failure_of_a_group_is_a_typed_error_then_any_non_cancellation():
  typed = TranscriptionJobError("timeout")
  group = BaseExceptionGroup("g", [asyncio.CancelledError(), ValueError("x"), ExceptionGroup("inner", [typed])])
  assert pl._first_error(group) is typed
  other = BaseExceptionGroup("g", [asyncio.CancelledError(), ValueError("x")])
  assert isinstance(pl._first_error(other), ValueError)
  only_cancel = BaseExceptionGroup("g", [asyncio.CancelledError()])
  assert isinstance(pl._first_error(only_cancel), asyncio.CancelledError)


@pytest.mark.asyncio
async def test_a_failing_chunk_stops_its_siblings_and_raises_the_typed_error(build, exports):
  pipeline = build()
  client = Client()
  started = []

  async def flaky(path, *, language, prompt=""):
    started.append(path.stem)
    if path.stem == "chunk_000":
      raise TranscriptionJobError("auth_error", detail="bad key")
    await asyncio.sleep(0.05)
    return {"language": None, "segments": []}

  client.transcribe = flaky
  with pytest.raises(TranscriptionJobError) as raised:
    await pipeline._transcribe(client, _chunks(6), pipeline.folder / "audio.wav")
  assert raised.value.code == "auth_error"


def test_the_ai_settings_failure_is_tolerated(monkeypatch, caplog):
  import app.ai.providers.factory as factory

  def boom(user_id=None):
    raise RuntimeError("no settings")

  monkeypatch.setattr(factory, "get_ai_settings", boom)
  with caplog.at_level(logging.WARNING):
    assert pl._user_settings("u1") == {}
  assert any("Could not load AI settings for transcription: no settings" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_the_chunk_folder_is_created_with_its_parents_and_reused(build, exports):
  import shutil

  pipeline = build()
  shutil.rmtree(pipeline.folder)
  await pipeline._transcribe(Client(), _chunks(1), pipeline.folder / "audio.wav")
  assert pipeline.chunk_dir.is_dir()
  await pipeline._transcribe(Client(), _chunks(1), pipeline.folder / "audio.wav")
