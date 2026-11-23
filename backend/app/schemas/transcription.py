from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MediaMetadata(BaseModel):
  title: str = Field(..., min_length=1, max_length=250)
  description: Optional[str] = Field(default="", max_length=2000)
  size_bytes: Optional[int] = None
  file_size_formatted: Optional[str] = None


class TranscriptionSegment(BaseModel):
  """Contract segment (docs/TRANSCRIPTION_PROCESS.md §4). `text_raw` is the literal provider output."""

  id: Optional[str] = None
  start: float
  end: float
  speaker: str = "Participante 1"
  speaker_id: Optional[str] = None
  text: str = ""
  text_raw: Optional[str] = None
  tags: List[str] = Field(default_factory=list)
  marked: bool = False


class TranscriptionSummary(BaseModel):
  summary_text: Optional[str] = None
  key_insights: List[str] = Field(default_factory=list)
  participants: List[str] = Field(default_factory=list)
  topics: List[str] = Field(default_factory=list)
  decisions: List[str] = Field(default_factory=list)
  requirements: List[str] = Field(default_factory=list)
  action_items: List[str] = Field(default_factory=list)
  template_id: Optional[str] = None
  template_name: Optional[str] = None


class TranscriptionProgress(BaseModel):
  """Progress snapshot (docs/TRANSCRIPTION_PROCESS.md §3)."""

  model_config = ConfigDict(extra="allow")

  id: str
  media_id: str
  title: Optional[str] = None
  status: str = "queued"
  stage: str = "queued"
  stage_progress: float = 0.0
  progress: int = 0
  message: str = ""
  preview: Optional[str] = None
  eta: Optional[str] = None
  eta_seconds: Optional[float] = None
  chunks_done: int = 0
  chunks_total: int = 0
  queue_position: Optional[int] = None
  model_info: Optional[str] = None
  error: Optional[str] = None
  error_code: Optional[str] = None
  retryable: bool = False
  summary_status: Optional[str] = None
  seq: int = 0
  timestamp: Optional[str] = None
  live_segments: List[Any] = Field(default_factory=list)
  live_text: Optional[str] = None


class TranscriptionResult(BaseModel):
  model_config = ConfigDict(extra="allow")

  id: str
  slug: Optional[str] = None
  media_id: Optional[str] = ""
  metadata: MediaMetadata
  language: str = "es"
  duration_seconds: float = 0.0
  created_at: str
  segments: List[TranscriptionSegment] = Field(default_factory=list)
  text: str = ""
  summary: Optional[TranscriptionSummary] = None
  saved_to_knowledge: bool = False
  document_id: Optional[str] = None


CleanupMode = Literal["off", "rules", "llm"]


class TranscribeRequest(BaseModel):
  transcription_id: Optional[str] = None
  language: Optional[str] = Field(default=None, max_length=10)
  diarize: Optional[bool] = None
  enable_diarization: Optional[bool] = None  # legacy alias of `diarize`
  num_speakers: Optional[int] = Field(default=None, ge=1, le=20)
  vocabulary: str = Field(default="", max_length=1000)
  cleanup: Optional[CleanupMode] = None
  summarize: bool = True
  # Legacy fields, accepted and ignored.
  mode: Optional[str] = None
  model_size: Optional[str] = None

  @property
  def wants_diarization(self) -> bool:
    if self.diarize is not None:
      return self.diarize
    return True if self.enable_diarization is None else self.enable_diarization


class UpdateSummaryRequest(BaseModel):
  summary: TranscriptionSummary


class RenameSpeakerRequest(BaseModel):
  speaker_map: dict[str, str]


class SpeakerMerge(BaseModel):
  model_config = ConfigDict(populate_by_name=True)

  source: str = Field(alias="from")
  into: str


class SpeakerEditRequest(BaseModel):
  rename: Optional[dict[str, str]] = None
  merge: Optional[List[SpeakerMerge]] = None


class SegmentEditRequest(BaseModel):
  speaker_id: Optional[str] = None
  new_speaker_name: Optional[str] = Field(default=None, max_length=80)
  text: Optional[str] = Field(default=None, max_length=20000)
  marked: Optional[bool] = None

  @model_validator(mode="after")
  def _one_speaker_change(self) -> "SegmentEditRequest":
    if self.speaker_id is not None and self.new_speaker_name is not None:
      raise ValueError("Indica speaker_id o new_speaker_name, no ambos.")
    return self


class SegmentSplitRequest(BaseModel):
  at: int = Field(..., ge=1)


class SaveToKnowledgeRequest(BaseModel):
  custom_tags: List[str] = Field(default_factory=list)


class SubmitClientTranscriptionRequest(BaseModel):
  id: str = Field(..., min_length=1, max_length=64)
  title: str = "Reunión"
  description: Optional[str] = ""
  language: str = "es"
  duration_seconds: float = 0.0
  text: str = ""
  segments: List[TranscriptionSegment] = Field(default_factory=list)
  generate_summary_now: bool = True
  # "browser": segments carry speaker ids from in-browser diarization (S1, S2…); otherwise one speaker.
  diarization: Optional[Literal["browser", "none"]] = None
