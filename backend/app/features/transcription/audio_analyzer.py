"""
Audio file analysis utilities using ffprobe.

Provides fast analysis of audio/video files without full conversion,
extracting duration, format, and validity information.
"""

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from app.core.exceptions import AudioAnalysisError

logger = logging.getLogger(__name__)


@dataclass
class AudioProperties:
    """Comprehensive audio file properties extracted from ffprobe."""
    
    duration_seconds: float
    sample_rate: int
    channels: int
    codec: str
    bitrate: int
    format: str
    file_size_bytes: int
    
    def __repr__(self) -> str:
        return (
            f"AudioProperties(duration={self.duration_seconds:.1f}s, "
            f"rate={self.sample_rate}Hz, channels={self.channels}, "
            f"codec={self.codec}, bitrate={self.bitrate}bps, "
            f"format={self.format}, size={self.file_size_bytes}B)"
        )


class AudioAnalyzer:
    """
    Analyzes audio/video files using ffprobe for metadata extraction.
    
    Provides fast analysis without full format conversion, suitable for
    determining if chunking is needed or validating file integrity.
    """
    
    # Supported audio and video formats
    SUPPORTED_AUDIO_FORMATS = {
        "mp3", "wav", "m4a", "aac", "ogg", "flac", "wma", "opus", "aiff",
    }
    SUPPORTED_VIDEO_FORMATS = {
        "mp4", "webm", "mkv", "avi", "mov", "wmv", "flv", "m4v", "3gp",
    }
    
    @staticmethod
    def _get_ffprobe_path() -> Optional[str]:
        """Locate ffprobe binary in system PATH."""
        try:
            result = subprocess.run(
                ["which", "ffprobe"] if Path("/bin/bash").exists() else ["where", "ffprobe"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        # Fallback: try common paths
        for path in ["/usr/bin/ffprobe", "/usr/local/bin/ffprobe", "ffprobe"]:
            if Path(path).exists() or path == "ffprobe":
                return path
        
        return None
    
    def get_duration_seconds(self, media_path: Path) -> float:
        """
        Extract audio/video duration using ffprobe.
        
        Uses ffprobe to quickly extract duration without full file processing.
        
        Args:
            media_path: Path to audio or video file
            
        Returns:
            Duration in seconds as float
            
        Raises:
            AudioAnalysisError: If file is invalid or ffprobe fails
        """
        if not media_path.exists():
            raise AudioAnalysisError(
                f"File not found",
                filename=media_path.name,
            )
        
        ffprobe = self._get_ffprobe_path()
        if not ffprobe:
            raise AudioAnalysisError(
                "ffprobe not found in PATH. Install ffmpeg to enable transcription.",
                filename=media_path.name,
            )
        
        try:
            cmd = [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(media_path),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode != 0:
                raise AudioAnalysisError(
                    f"ffprobe failed: {result.stderr.strip()}",
                    filename=media_path.name,
                )
            
            stdout_str = result.stdout.strip()
            if stdout_str.startswith("{"):
                try:
                    data = json.loads(stdout_str)
                    duration = float(data.get("format", {}).get("duration", 0))
                except Exception:
                    duration = 0.0
            else:
                duration = float(stdout_str)

            if duration <= 0:
                raise ValueError("Duration is zero or negative")
            return duration
        except (ValueError, TypeError) as e:
            raise AudioAnalysisError(
                f"Could not parse duration from ffprobe output: {e}",
                filename=media_path.name,
            )
        except (subprocess.TimeoutExpired, TimeoutError):
            raise AudioAnalysisError(
                "ffprobe timeout (file may be corrupted)",
                filename=media_path.name,
            )
        except AudioAnalysisError:
            raise
        except Exception as e:
            raise AudioAnalysisError(
                f"Unexpected error analyzing audio: {e}",
                filename=media_path.name,
            )

    def validate_audio_integrity(self, media_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Validate that audio file is not corrupted and has proper audio stream.
        
        Checks:
        - File is readable by ffprobe
        - Has valid audio stream
        - Duration is positive
        - Format is in supported list
        
        Args:
            media_path: Path to audio or video file
            
        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if file is valid, False otherwise
            - error_message: None if valid, descriptive error if invalid
        """
        if not media_path.exists():
            return False, f"File not found: {media_path.name}"

        ext = media_path.suffix.lower().lstrip(".")
        if ext and ext not in (self.SUPPORTED_AUDIO_FORMATS | self.SUPPORTED_VIDEO_FORMATS):
            return False, f"Unsupported file format: .{ext}"
            return False, f"File not found: {media_path.name}"
        
        ffprobe = self._get_ffprobe_path()
        if not ffprobe:
            return False, "ffprobe not found in PATH"
        
        try:
            # Get comprehensive format and stream info
            cmd = [
                ffprobe,
                "-v", "error",
                "-show_format",
                "-show_streams",
                "-of", "json",
                str(media_path),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode != 0:
                return False, f"File analysis failed: {result.stderr.strip()}"
            
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                return False, "Invalid JSON from ffprobe (file may be corrupted)"
            
            # Check format exists
            fmt = data.get("format")
            if not fmt:
                return False, "No format information in file"
            
            # Check duration
            try:
                duration = float(fmt.get("duration", 0))
                if duration <= 0:
                    return False, "File has zero or negative duration"
            except (ValueError, TypeError):
                return False, "Could not parse file duration"
            
            # Check for audio stream
            streams = data.get("streams", [])
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
            if not has_audio:
                return False, "File has no audio stream"
            
            # Check file format
            format_name = fmt.get("format_name", "").lower()
            file_ext = media_path.suffix.lower().lstrip(".")
            
            valid_formats = (
                self.SUPPORTED_AUDIO_FORMATS | 
                self.SUPPORTED_VIDEO_FORMATS
            )
            if file_ext not in valid_formats:
                return False, f"Unsupported format: {file_ext}"
            
            logger.info(
                f"Audio file validated: {media_path.name} "
                f"({duration:.1f}s, format={format_name})"
            )
            return True, None
        
        except subprocess.TimeoutExpired:
            return False, "Analysis timeout (file may be corrupted)"
        except Exception as e:
            return False, f"Analysis error: {e}"
    
    def get_audio_properties(self, media_path: Path) -> AudioProperties:
        """
        Extract comprehensive audio properties from file.
        
        Uses ffprobe to get detailed information about the audio stream.
        
        Args:
            media_path: Path to audio or video file
            
        Returns:
            AudioProperties dataclass with all extracted properties
            
        Raises:
            AudioAnalysisError: If file analysis fails
        """
        if not media_path.exists():
            raise AudioAnalysisError(
                "File not found",
                filename=media_path.name,
            )
        
        ffprobe = self._get_ffprobe_path()
        if not ffprobe:
            raise AudioAnalysisError(
                "ffprobe not found in PATH",
                filename=media_path.name,
            )
        
        try:
            cmd = [
                ffprobe,
                "-v", "error",
                "-show_format",
                "-show_streams",
                "-of", "json",
                str(media_path),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode != 0:
                raise AudioAnalysisError(
                    f"ffprobe failed: {result.stderr.strip()}",
                    filename=media_path.name,
                )
            
            data = json.loads(result.stdout)
            fmt = data.get("format", {})
            
            # Find audio stream
            audio_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "audio":
                    audio_stream = stream
                    break
            
            if not audio_stream:
                raise AudioAnalysisError(
                    "No audio stream found",
                    filename=media_path.name,
                )
            
            # Extract properties
            duration = float(fmt.get("duration", 0))
            sample_rate = int(audio_stream.get("sample_rate", 0))
            channels = int(audio_stream.get("channels", 0))
            codec = audio_stream.get("codec_name", "unknown")
            bitrate = int(audio_stream.get("bit_rate", 0))
            format_name = fmt.get("format_name", "unknown")
            file_size = media_path.stat().st_size
            
            props = AudioProperties(
                duration_seconds=duration,
                sample_rate=sample_rate,
                channels=channels,
                codec=codec,
                bitrate=bitrate,
                format=format_name,
                file_size_bytes=file_size,
            )
            
            logger.info(f"Analyzed audio properties: {props}")
            return props
        
        except subprocess.TimeoutExpired:
            raise AudioAnalysisError(
                "ffprobe timeout",
                filename=media_path.name,
            )
        except json.JSONDecodeError:
            raise AudioAnalysisError(
                "Invalid ffprobe output",
                filename=media_path.name,
            )
        except AudioAnalysisError:
            raise
        except Exception as e:
            raise AudioAnalysisError(
                f"Unexpected error: {e}",
                filename=media_path.name,
            )
