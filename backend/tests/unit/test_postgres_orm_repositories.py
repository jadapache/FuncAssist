"""Tests verifying PostgreSQL ORM repositories and models using SQLAlchemy."""

import pytest

from app.db.database import set_session_override, set_sync_session_override
from app.db.models import (
  AIModelCatalogModel,
  ChatMessageModel,
  CorporateTemplateModel,
  PRDReviewModel,
  StandupModel,
  TestPlanModel,
  TranscriptionModel,
  UserModel,
)
from app.db.repositories import (
  AIModelCatalogRepository,
  ChatRepository,
  CorporateTemplateRepository,
  PRDRepository,
  StandupRepository,
  TestPlanRepository,
  TranscriptionRepository,
  UserRepository,
)
from tests.fake_session import GLOBAL_FAKE_STORAGE, fake_async_db, fake_sync_db


@pytest.fixture(autouse=True)
def setup_fake_db():
  GLOBAL_FAKE_STORAGE.clear()
  set_session_override(fake_async_db)
  set_sync_session_override(fake_sync_db)
  yield
  GLOBAL_FAKE_STORAGE.clear()
  set_session_override(None)
  set_sync_session_override(None)


@pytest.mark.asyncio
async def test_user_repository_orm_crud():
  repo = UserRepository()

  # 1. Count should start at 0
  assert await repo.count() == 0

  # 2. First user created becomes admin and approved automatically
  admin = await repo.create_user_with_password(
    username="admin_test",
    password_hash="hash123",
    password_salt="salt123",
    email="admin@test.com",
    full_name="Admin QA",
  )
  assert admin["role"] == "admin"
  assert admin["status"] == "approved"
  assert await repo.count() == 1

  # 3. Second user becomes pending
  user2 = await repo.create_user_with_password(
    username="dev_bob",
    password_hash="hash456",
    password_salt="salt456",
    role="dev",
  )
  assert user2["status"] == "pending"
  assert user2["role"] == "dev"
  assert await repo.count() == 2

  # 4. Get by username and ID
  found = await repo.get_by_username("dev_bob")
  assert found is not None
  assert found["id"] == user2["id"]

  # 5. Get pending users
  pending = await repo.get_pending_users()
  assert len(pending) == 1
  assert pending[0]["username"] == "dev_bob"

  # 6. Update user status
  updated = await repo.update_user_status(user2["id"], "approved")
  assert updated is not None
  assert updated["status"] == "approved"

  # 7. Update profile
  updated_profile = await repo.update(user2["id"], {"full_name": "Bob Developer"})
  assert updated_profile["full_name"] == "Bob Developer"

  # 8. Delete user
  deleted = await repo.delete(user2["id"])
  assert deleted is True
  assert await repo.count() == 1


@pytest.mark.asyncio
async def test_chat_repository_orm():
  repo = ChatRepository()

  msg = await repo.save_message(
    session_id="sess-100",
    role="user",
    content="Hello QA",
    context_sources=[{"doc_id": "1"}],
  )
  assert msg["session_id"] == "sess-100"
  assert msg["content"] == "Hello QA"

  msgs = await repo.get_session_messages("sess-100")
  assert len(msgs) == 1
  assert msgs[0]["id"] == msg["id"]

  cleared = await repo.clear_session("sess-100")
  assert cleared is True
  assert len(await repo.get_session_messages("sess-100")) == 0


@pytest.mark.asyncio
async def test_standup_repository_orm():
  repo = StandupRepository()

  standup = await repo.create_standup(
    title="Daily Standup",
    content="Tested authentication feature",
    sources=["Jira-123"],
  )
  assert standup["title"] == "Daily Standup"

  items = await repo.get_all_standups()
  assert len(items) == 1
  assert items[0]["title"] == "Daily Standup"


@pytest.mark.asyncio
async def test_prd_repository_orm():
  repo = PRDRepository()

  prd = await repo.create_prd_review(
    prd_title="User Onboarding",
    content="Good specifications",
    score=85,
    risk_level="LOW",
  )
  assert prd["prd_title"] == "User Onboarding"
  assert prd["score"] == 85

  reviews = await repo.get_all_prd_reviews()
  assert len(reviews) == 1
  assert reviews[0]["prd_title"] == "User Onboarding"


@pytest.mark.asyncio
async def test_test_plan_repository_orm():
  repo = TestPlanRepository()

  plan = await repo.create_test_plan(
    feature_name="Payment Gateway",
    content="Step 1: Test card validation",
    test_type="regression",
  )
  assert plan["feature_name"] == "Payment Gateway"

  plans = await repo.get_all_test_plans()
  assert len(plans) == 1
  assert plans[0]["feature_name"] == "Payment Gateway"


def test_transcription_repository_crud():
  repo = TranscriptionRepository()

  record = {
    "id": "tx-1001",
    "title": "Daily Planning Sprint 24",
    "description": "Team planning meeting",
    "original_filename": "meeting.wav",
    "stored_filename": "audio.wav",
    "path": "c:/Dev/QA_MGMT/local/transcriptions/tx-1001/audio.wav",
    "duration_seconds": 125.5,
    "language": "es",
    "status": "completed",
    "model_info": "Whisper Large",
    "text": "Bienvenidos a la planeación del sprint.",
    "segments": [{"start": 0.0, "end": 4.5, "text": "Bienvenidos a la planeación.", "speaker": "Speaker 1"}],
    "summary": {"topics": ["Sprint 24", "QA Automation"], "decisions": ["Deploy to staging on Thursday"]},
  }

  # 1. Upsert
  saved = repo.upsert_sync(record)
  assert saved["id"] == "tx-1001"
  assert saved["title"] == "Daily Planning Sprint 24"
  assert saved["duration_seconds"] == 125.5
  assert len(saved["segments"]) == 1
  assert saved["summary"]["topics"] == ["Sprint 24", "QA Automation"]

  # 2. Get
  fetched = repo.get_sync("tx-1001")
  assert fetched is not None
  assert fetched["text"] == "Bienvenidos a la planeación del sprint."

  # 3. List
  all_items = repo.list_sync()
  assert len(all_items) == 1
  assert all_items[0]["id"] == "tx-1001"

  # 4. Delete
  deleted = repo.delete_sync("tx-1001")
  assert deleted is True
  assert repo.get_sync("tx-1001") is None


@pytest.mark.asyncio
async def test_corporate_template_repository_crud():
  repo = CorporateTemplateRepository()

  tmpl = {
    "id": "corp-tpl-1",
    "title": "Acta de Reunión Corporativa",
    "filename": "acta_reunion.docx",
    "stored_filename": "corp-tpl-1.docx",
    "file_type": "docx",
    "file_size": 15420,
    "module": "qa",
    "tags": ["NECESIDAD", "ACUERDOS"],
    "custom_content": "# Acta de Reunión",
  }

  saved = await repo.upsert(tmpl)
  assert saved["id"] == "corp-tpl-1"
  assert saved["title"] == "Acta de Reunión Corporativa"
  assert saved["tags"] == ["NECESIDAD", "ACUERDOS"]

  fetched = await repo.get("corp-tpl-1")
  assert fetched is not None
  assert fetched["custom_content"] == "# Acta de Reunión"

  all_tmpls = await repo.list()
  assert len(all_tmpls) == 1

  assert await repo.delete("corp-tpl-1") is True
  assert await repo.get("corp-tpl-1") is None


def test_ai_model_catalog_repository():
  repo = AIModelCatalogRepository()

  models = [
    {
      "id": "llama-3.3-70b-versatile",
      "provider": "groq",
      "task_type": "chat_writing",
      "name": "Llama 3.3 70B",
      "is_free": True,
      "context_length": 131072,
    },
    {
      "id": "whisper-large-v3",
      "provider": "groq",
      "task_type": "transcription",
      "name": "Whisper Large v3 (Groq)",
      "is_free": True,
      "context_length": 0,
    },
  ]

  count = repo.bulk_upsert_sync(models)
  assert count == 2

  chat_models = repo.list_sync(task_type="chat_writing")
  assert len(chat_models) == 1
  assert chat_models[0]["id"] == "llama-3.3-70b-versatile"

  single = repo.get_sync("whisper-large-v3")
  assert single is not None
  assert single["provider"] == "groq"
