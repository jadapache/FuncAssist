"""Which chat messages a draft save writes to the database and which it skips as already stored."""

from __future__ import annotations

import pytest

from app.api.drafts import _store_new_messages


class FakeRepo:
  def __init__(self, existing):
    self.existing = existing
    self.reads = []
    self.saved = []

  async def get_session_messages(self, **kwargs):
    self.reads.append(kwargs)
    return self.existing

  async def save_message(self, **kwargs):
    self.saved.append(kwargs)


async def store(existing, messages):
  repo = FakeRepo(existing)
  await _store_new_messages(repo, messages, "s1", "u1")
  return repo


@pytest.mark.asyncio
async def test_the_stored_messages_are_read_for_this_session_and_user_without_a_limit():
  repo = await store([], [])
  assert repo.reads == [{"session_id": "s1", "limit": 0, "user_id": "u1"}]
  assert repo.saved == []


@pytest.mark.asyncio
async def test_a_new_message_is_saved_with_everything_it_carries():
  message = {"id": "m1", "role": "assistant", "content": "  hola  ", "context_sources": ["jira"], "attachments": ["a"]}
  repo = await store([], [message])
  assert repo.saved == [{
    "session_id": "s1", "role": "assistant", "content": "hola", "context_sources": ["jira"],
    "attachments": ["a"], "user_id": "u1", "id": "m1",
  }]


@pytest.mark.asyncio
async def test_a_message_without_a_role_is_from_the_user_and_optional_fields_are_empty():
  (saved,) = (await store([], [{"content": "hola"}])).saved
  assert (saved["role"], saved["id"], saved["context_sources"], saved["attachments"]) == ("user", None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("message", [{"content": ""}, {"content": "   "}, {}, {"content": None}, {"id": "m1", "content": " "}])
async def test_messages_without_text_are_skipped(message):
  assert (await store([], [message])).saved == []


@pytest.mark.asyncio
async def test_a_message_with_an_id_is_skipped_only_when_the_stored_one_has_the_same_text():
  existing = [{"id": "m1", "role": "user", "content": " hola "}]
  repo = await store(existing, [
    {"id": "m1", "role": "user", "content": "hola"},
    {"id": "m1", "role": "user", "content": "hola editado"},
    {"id": "m2", "role": "user", "content": "hola"},
  ])
  assert [(m["id"], m["content"]) for m in repo.saved] == [("m1", "hola editado"), ("m2", "hola")]


@pytest.mark.asyncio
async def test_a_message_without_an_id_is_skipped_when_the_same_role_already_said_the_same_text():
  existing = [{"role": "assistant", "content": "ok"}, {"id": "m1", "role": "user", "content": "hola"}]
  repo = await store(existing, [
    {"role": "assistant", "content": "ok"},
    {"role": "user", "content": "ok"},
    {"content": "hola"},
  ])
  assert [(m["role"], m["content"]) for m in repo.saved] == [("user", "ok")]


@pytest.mark.asyncio
async def test_a_repeated_text_without_an_id_is_saved_once_per_save():
  repo = await store([], [{"content": "sí"}, {"content": "sí"}, {"role": "assistant", "content": "sí"}])
  assert [(m["role"], m["content"]) for m in repo.saved] == [("user", "sí"), ("assistant", "sí")]


@pytest.mark.asyncio
async def test_messages_with_an_id_keep_repeated_texts():
  repo = await store([], [{"id": "a", "content": "ok"}, {"id": "b", "content": "ok"}])
  assert [m["id"] for m in repo.saved] == ["a", "b"]
