import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Tuple

from app.core.settings import BIN_DIR
from app.core.exceptions import FFmpegError

logger = logging.getLogger(__name__)

_CACHED_FFMPEG_PATH: str | None = None


def _ensure_in_path(directory: Path) -> None:
    dir_str = str(directory)
    current_path = os.environ.get("PATH", "")
    paths = current_path.split(os.pathsep)
    if dir_str not in paths:
        os.environ["PATH"] = dir_str + os.pathsep + current_path


def get_ffmpeg_binary() -> str | None:
    global _CACHED_FFMPEG_PATH
    if _CACHED_FFMPEG_PATH and Path(_CACHED_FFMPEG_PATH).is_file():
        return _CACHED_FFMPEG_PATH

    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    target = BIN_DIR / exe_name

    if target.is_file() and target.stat().st_size > 10000:
        _ensure_in_path(BIN_DIR)
        _CACHED_FFMPEG_PATH = str(target.resolve())
        return _CACHED_FFMPEG_PATH

    resolved = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if resolved and Path(resolved).is_file():
        _CACHED_FFMPEG_PATH = str(Path(resolved).resolve())
        return _CACHED_FFMPEG_PATH

    return None


def ensure_ffmpeg_in_user_data() -> str | None:
    return get_ffmpeg_binary()


def ensure_ffmpeg_available() -> str:
    """Ensure FFmpeg is available, raise error if not."""
    ffmpeg = get_ffmpeg_binary()
    if not ffmpeg:
        error_msg = (
            "FFmpeg is not installed or not in PATH. "
            "MP3 and other compressed formats require FFmpeg. "
            "Install via: brew install ffmpeg (Mac), apt-get install ffmpeg (Linux), "
            "or choco install ffmpeg (Windows)"
        )
        logger.error(error_msg)
        raise FFmpegError(error_msg)
    return ffmpeg


def extract_audio_track(
    media_path: Path,
    output_wav_path: Path,
    validate: bool = True,
) -> Tuple[Path, bool]:
    """
    Extract audio from video or audio file to 16 kHz mono WAV using ffmpeg.
    
    Args:
        media_path: Path to source media file
        output_wav_path: Path where WAV file should be written
        validate: If True, validate the output file after extraction
        
    Returns:
        Tuple of (output_path, success_flag)
        - output_path: Path to the WAV file (output_wav_path if successful, media_path if already WAV)
        - success_flag: True if extraction was successful or file was already WAV
        
    Raises:
        FFmpegError: If FFmpeg processing fails and validation is enabled
    """
    suffix = media_path.suffix.lower()
    if suffix == ".wav":
        # Already WAV, no conversion needed
        return media_path, True

    ffmpeg_cmd = ensure_ffmpeg_available()  # ← Valida disponibilidad temprana

    try:
        cmd = [
            ffmpeg_cmd,
            "-y",
            "-i",
            str(media_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output_wav_path),
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        
        if result.returncode != 0:
            error_msg = f"FFmpeg conversion failed"
            logger.error(f"{error_msg}: {result.stderr}")
            raise FFmpegError(
                error_msg,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        
        # Validate output file if requested
        if validate:
            _validate_output_wav(output_wav_path, media_path)
        
        logger.info(f"Successfully extracted audio: {media_path.name} → {output_wav_path.name}")
        return output_wav_path, True
    
    except FFmpegError:
        raise
    except (subprocess.TimeoutExpired, TimeoutError):
        error_msg = "FFmpeg audio extraction timeout"
        logger.error(error_msg)
        raise FFmpegError(error_msg)
    except Exception as exc:
        error_msg = f"Unexpected error during FFmpeg audio extraction: {exc}"
        logger.error(error_msg)
        raise FFmpegError(error_msg)


def _validate_output_wav(output_path: Path, source_path: Path) -> None:
    """
    Validate that FFmpeg output is a valid WAV file.
    
    Checks:
    - Output file exists and is not empty
    - Output file can be read by ffprobe
    - Output file has reasonable duration
    
    Args:
        output_path: Path to the generated WAV file
        source_path: Path to the original source file (for comparison)
        
    Raises:
        FFmpegError: If validation fails
    """
    # Check file exists and has size
    if not output_path.exists():
        raise FFmpegError(f"Output file was not created: {output_path}")
    
    file_size = output_path.stat().st_size
    if file_size == 0:
        raise FFmpegError(f"Output file is empty (0 bytes): {output_path}")
    
    if file_size < 1000:  # Less than 1KB is suspiciously small
        logger.warning(f"Output file is very small ({file_size} bytes): {output_path}")
    
    # Verify with ffprobe that output is readable and has valid audio
    ffprobe_cmd = shutil.which("ffprobe")
    if not ffprobe_cmd:
        logger.warning("ffprobe not available for output validation")
        return
    
    try:
        result = subprocess.run(
            [
                ffprobe_cmd,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode != 0:
            raise FFmpegError(f"Output WAV validation failed: {result.stderr}")
        
        try:
            duration = float(result.stdout.strip())
            if duration <= 0:
                raise FFmpegError(f"Output WAV has zero or negative duration: {duration}s")
            logger.debug(f"Output WAV validated: {duration:.1f}s duration")
        except ValueError:
            raise FFmpegError(f"Could not parse output WAV duration: {result.stdout}")
    
    except subprocess.TimeoutExpired:
        raise FFmpegError("Output WAV validation timeout")


def compress_audio_opus(
    media_path: Path,
    output_path: Path,
    bitrate: str = "32k",
    sample_rate: int = 16000,
) -> Path:
    """
    Compress audio to Opus format for maximum size reduction.
    
    Opus at 32kbps provides better quality than MP3 at 48kbps
    and is ideal for speech transcription.
    
    Args:
        media_path: Path to source audio file
        output_path: Path where Opus file should be written
        bitrate: Bitrate for Opus encoding (default 32k)
        sample_rate: Sample rate in Hz (default 16000)
        
    Returns:
        Path to the compressed Opus file
        
    Raises:
        FFmpegError: If compression fails
    """
    ffmpeg_cmd = ensure_ffmpeg_available()
    
    try:
        cmd = [
            ffmpeg_cmd,
            "-y",
            "-i",
            str(media_path),
            "-c:a", "libopus",
            "-b:a", bitrate,
            "-ar", str(sample_rate),
            "-ac", "1",
            str(output_path),
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        
        if result.returncode != 0:
            raise FFmpegError(
                "Opus compression failed",
                stderr=result.stderr,
                returncode=result.returncode,
            )
        
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise FFmpegError(f"Opus compression produced empty file")
        
        source_size = media_path.stat().st_size
        output_size = output_path.stat().st_size
        reduction = 100 * (1 - output_size / source_size) if source_size > 0 else 0
        
        logger.info(
            f"Audio compressed with Opus: "
            f"{source_size / 1024 / 1024:.1f}MB → {output_size / 1024 / 1024:.1f}MB "
            f"({reduction:.1f}% reduction)"
        )
        
        return output_path
    
    except (subprocess.TimeoutExpired, TimeoutError):
        raise FFmpegError("Opus compression timeout")
    except FFmpegError:
        raise
    except Exception as exc:
        raise FFmpegError(f"Unexpected error during Opus compression: {exc}")


def convert_to_format(
    media_path: Path,
    output_path: Path,
    output_format: str = "wav",
    audio_codec: str = "pcm_s16le",
    sample_rate: int = 16000,
    channels: int = 1,
    bitrate: str = "128k",
    timeout: int = 3600,
) -> Path:
    """
    Universal audio/video format conversion using FFmpeg.
    
    Converts any media format to specified output format with consistent parameters.
    Optimal for transcription: 16 kHz mono PCM WAV by default.
    
    Args:
        media_path: Path to source media file (any format)
        output_path: Path where converted file should be written
        output_format: Output format (wav, mp3, flac, opus, aac, etc.)
        audio_codec: Audio codec to use (pcm_s16le, libmp3lame, libflac, libopus, aac, etc.)
        sample_rate: Sample rate in Hz (default 16000 for Whisper)
        channels: Number of channels (default 1 for mono)
        bitrate: Bitrate (only for lossy formats like MP3)
        timeout: Timeout in seconds (default 3600)
        
    Returns:
        Path to the converted file
        
    Raises:
        FFmpegError: If conversion fails
    """
    if not media_path.exists():
        raise FFmpegError(f"Source file not found: {media_path}")
    
    ffmpeg_cmd = ensure_ffmpeg_available()
    
    try:
        # Build FFmpeg command
        cmd = [
            ffmpeg_cmd,
            "-y",                          # Overwrite output without asking
            "-i", str(media_path),          # Input file
            "-vn",                          # No video
            "-acodec", audio_codec,         # Audio codec
            "-ar", str(sample_rate),        # Sample rate
            "-ac", str(channels),           # Number of channels
        ]
        
        # Add bitrate only for lossy formats
        if audio_codec in ("libmp3lame", "libopus", "aac", "libvorbis"):
            cmd.extend(["-b:a", bitrate])
        
        cmd.append(str(output_path))
        
        logger.info(
            f"Converting {media_path.name} → {output_format}: "
            f"{audio_codec} {sample_rate}Hz {channels}ch"
        )
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        
        if result.returncode != 0:
            raise FFmpegError(
                f"FFmpeg conversion to {output_format} failed",
                stderr=result.stderr,
                returncode=result.returncode,
            )
        
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise FFmpegError(
                f"Conversion produced empty file: {output_path}"
            )
        
        source_size = media_path.stat().st_size
        output_size = output_path.stat().st_size
        logger.info(
            f"Conversion successful: {source_size / 1024 / 1024:.1f}MB → "
            f"{output_size / 1024 / 1024:.1f}MB"
        )
        
        return output_path
    
    except subprocess.TimeoutExpired:
        raise FFmpegError(f"FFmpeg conversion timeout ({timeout}s)")
    except FFmpegError:
        raise
    except Exception as exc:
        raise FFmpegError(f"Unexpected error during format conversion: {exc}")
