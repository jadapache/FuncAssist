from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from app.core.settings import WHISPER_MODELS_DIR
from app.features.transcription.providers.base import (
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
)

logger = logging.getLogger(__name__)


def load_audio_16k_mono(audio_path: Path) -> np.ndarray:
    """Decode any audio file into 16kHz mono float32 samples using PyAV."""
    import av

    container = av.open(str(audio_path))
    resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
    samples_list: List[np.ndarray] = []

    for frame in container.decode(audio=0):
        for resampled in resampler.resample(frame):
            arr = resampled.to_ndarray()[0]
            samples_list.append(arr)

    container.close()
    if samples_list:
        return np.concatenate(samples_list).astype(np.float32)
    return np.array([], dtype=np.float32)


class OnnxTranscriptionProvider(TranscriptionProvider):
    provider_id = "onnx"
    display_name = "ONNX Runtime (Parakeet / SenseVoice / Moonshine / Whisper)"

    HF_REPOS: Dict[str, str] = {
        "parakeet-multilingual-es": "csukuangfj/sherpa-onnx-nemo-fast-conformer-ctc-be-de-en-es-fr-hr-it-pl-ru-uk-2024-07-16",
        "parakeet-ctc-0.6b": "csukuangfj/sherpa-onnx-nemo-ctc-en-conformer-small",
        "sense-voice-small": "FunAudioLLM/SenseVoiceSmall",
        "moonshine-onnx-tiny": "csukuangfj/sherpa-onnx-moonshine-tiny-en-int8",
        "whisper-onnx-tiny": "csukuangfj/sherpa-onnx-whisper-tiny",
    }

    def is_available(self) -> bool:
        try:
            import onnxruntime  # noqa: F401
            import sherpa_onnx  # noqa: F401
            return True
        except ImportError:
            return False

    def _model_dir(self, model_id: str) -> Path:
        clean = model_id.strip().lower()
        return WHISPER_MODELS_DIR / f"onnx-{clean}"

    def get_model_path(self, model_id: str) -> Optional[Path]:
        d = self._model_dir(model_id)
        if d.exists() and any(d.glob("*.onnx")):
            return d
        return None

    def is_model_downloaded(self, model_id: str) -> bool:
        return self.get_model_path(model_id) is not None

    def _build_recognizer(self, model_dir: Path, model_id: str, language: Optional[str] = None):
        import sherpa_onnx

        # Find .onnx and tokens.txt in model_dir
        onnx_files = list(model_dir.glob("*.onnx"))
        token_files = list(model_dir.glob("*tokens*.txt")) or list(model_dir.glob("tokens.txt"))
        tokens_path = str(token_files[0]) if token_files else ""

        if "sense-voice" in model_id.lower() or "sensevoice" in model_id.lower():
            model_file = next((str(f) for f in onnx_files if "model" in f.name.lower()), str(onnx_files[0]))
            return sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=model_file,
                tokens=tokens_path,
                num_threads=4,
                language=language or "auto",
                use_itn=True,
            )

        if "parakeet" in model_id.lower() or "nemo" in model_id.lower():
            model_file = next((str(f) for f in onnx_files if "model" in f.name.lower()), str(onnx_files[0]))
            return sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
                model=model_file,
                tokens=tokens_path,
                num_threads=4,
            )

        if "moonshine" in model_id.lower():
            prep = next((str(f) for f in onnx_files if "preprocess" in f.name.lower()), "")
            enc = next((str(f) for f in onnx_files if "encoder" in f.name.lower()), "")
            uncached = next((str(f) for f in onnx_files if "uncached" in f.name.lower()), "")
            cached = next((str(f) for f in onnx_files if "cached" in f.name.lower() and "uncached" not in f.name.lower()), "")
            return sherpa_onnx.OfflineRecognizer.from_moonshine(
                preprocessor=prep,
                encoder=enc,
                uncached_decoder=uncached,
                cached_decoder=cached,
                tokens=tokens_path,
                num_threads=4,
            )

        if "whisper" in model_id.lower():
            enc = next((str(f) for f in onnx_files if "encoder" in f.name.lower()), "")
            dec = next((str(f) for f in onnx_files if "decoder" in f.name.lower()), "")
            return sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=enc,
                decoder=dec,
                tokens=tokens_path,
                num_threads=4,
                language=language or "es",
                task="transcribe",
            )

        # Fallback to NeMo CTC generic recognizer
        model_file = str(onnx_files[0]) if onnx_files else ""
        return sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
            model=model_file,
            tokens=tokens_path,
            num_threads=4,
        )

    def transcribe(
        self,
        audio_path: Path,
        model_id: str,
        language: Optional[str] = None,
        on_progress: Optional[Callable[[int, str, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> TranscriptionResult:
        if not self.is_available():
            raise RuntimeError("Se requieren onnxruntime y sherpa-onnx para este motor.")

        model_dir = self.get_model_path(model_id)
        if not model_dir:
            raise FileNotFoundError(
                f"El modelo ONNX '{model_id}' no está descargado. Descárguelo desde Ajustes antes de transcribir."
            )

        logger.info(f"Loading ONNX STT model '{model_id}' from {model_dir}")
        if on_progress:
            on_progress(15, f"Cargando modelo ONNX {model_id}...", "")

        samples = load_audio_16k_mono(audio_path)
        sample_rate = 16000
        duration_sec = len(samples) / sample_rate if len(samples) > 0 else 1.0

        recognizer = self._build_recognizer(model_dir, model_id, language=language)

        if cancel_check and cancel_check():
            raise RuntimeError("Transcripción cancelada por el usuario.")

        if on_progress:
            on_progress(35, "Procesando audio con ONNX Runtime...", "")

        # Process audio in 30-second chunks for progress tracking and timestamp segmentation
        chunk_size_samples = 30 * sample_rate
        segments: List[TranscriptionSegment] = []
        full_text_parts: List[str] = []

        total_chunks = max(1, int(np.ceil(len(samples) / chunk_size_samples)))

        for i in range(total_chunks):
            if cancel_check and cancel_check():
                raise RuntimeError("Transcripción cancelada por el usuario.")

            start_idx = i * chunk_size_samples
            end_idx = min(len(samples), (i + 1) * chunk_size_samples)
            chunk_samples = samples[start_idx:end_idx]

            chunk_start_sec = start_idx / sample_rate
            chunk_end_sec = end_idx / sample_rate

            stream = recognizer.create_stream()
            stream.accept_waveform(sample_rate, chunk_samples)
            recognizer.decode_stream(stream)

            res = stream.result
            text = (res.text if hasattr(res, "text") else str(res)).strip()

            if text:
                segments.append(
                    TranscriptionSegment(
                        start=round(chunk_start_sec, 2),
                        end=round(chunk_end_sec, 2),
                        text=text,
                        speaker=f"Participante {(i % 2) + 1}",
                    )
                )
                full_text_parts.append(text)

            if on_progress:
                pct = min(85, 35 + int(((i + 1) / total_chunks) * 50))
                on_progress(pct, f"Procesado {(i+1)}/{total_chunks} fragmentos...", "")

        full_text = " ".join(full_text_parts)

        return TranscriptionResult(
            language=language or ("en" if "en" in model_id.lower() else "es"),
            text=full_text,
            segments=segments,
            duration=round(duration_sec, 2),
            provider=self.provider_id,
            engine="onnxruntime",
            model_id=model_id,
        )
