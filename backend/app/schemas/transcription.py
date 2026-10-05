from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class MediaMetadata(BaseModel):
  title: str = Field(..., min_length=1, max_length=250)
  description: Optional[str] = Field(default="", max_length=2000)
  size_bytes: Optional[int] = None
  file_size_formatted: Optional[str] = None


class TranscriptionSegment(BaseModel):
  start: float
  end: float
  speaker: str = "Participante 1"
  text: str


class TranscriptionSummary(BaseModel):
  summary_text: Optional[str] = None
  key_insights: List[str] = Field(default_factory=list)
  participants: List[str] = Field(default_factory=list)
  topics: List[str] = Field(default_factory=list)
  decisions: List[str] = Field(default_factory=list)
  requirements: List[str] = Field(default_factory=list)
  action_items: List[str] = Field(default_factory=list)



class TranscriptionProgress(BaseModel):
  id: str
  media_id: str
  status: str = "pending"  # pending, uploading, preprocessing, transcribing, diarizing, summarizing, complete, failed, cancelled
  stage: str = "pending"
  progress: int = 0  # 0 to 100
  message: str = ""
  preview: Optional[str] = None
  eta: Optional[str] = None
  model_info: Optional[str] = None
  error: Optional[str] = None
  timestamp: Optional[str] = None


class TranscriptionResult(BaseModel):
  id: str
  media_id: str
  metadata: MediaMetadata
  language: str = "es"
  duration_seconds: float = 0.0
  created_at: str
  segments: List[TranscriptionSegment] = Field(default_factory=list)
  text: str = ""
  summary: Optional[TranscriptionSummary] = None
  saved_to_knowledge: bool = False
  document_id: Optional[str] = None


class TranscribeRequest(BaseModel):
  transcription_id: Optional[str] = None
  mode: str = "auto"  # auto, local, cloud, groq, openai
  language: Optional[str] = None
  model_size: Optional[str] = None
  enable_diarization: bool = True


class UpdateSummaryRequest(BaseModel):
  summary: TranscriptionSummary


class RenameSpeakerRequest(BaseModel):
  speaker_map: dict[str, str]


class SaveToKnowledgeRequest(BaseModel):
  custom_tags: List[str] = Field(default_factory=list)
