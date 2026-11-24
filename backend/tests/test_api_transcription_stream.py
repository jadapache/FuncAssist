"""Tests for the transcription SSE progress stream (app/api/transcription_stream.py)."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import transcription as tr
from app.api import transcription_stream as ts

USER_ID = "test-user-id"


class FakeJobs:
  def __init__(self, running=True, snap=None):
    self.running = running
    self.snap = snap

  def snapshot(self, job_id):
    return self.snap

  def is_running(self, job_id):
    r = self.running
    if isinstance(r, list):
      return r.pop(0) if r else False
    return r


@pytest.fixture
def jobs(monkeypatch):
  fj = FakeJobs()
  monkeypatch.setattr(ts, "job_manager", fj)
  return fj


async def _collect(gen):
  return [x async for x in gen]


def test_formatters():
  assert ts.format_event({"seq": 4, "a": "é"}, "v2") == 'id: 4\nevent: progress\ndata: {"seq": 4, "a": "é"}\n\n'
  assert ts.format_event({"a": 1}, "v1") == 'data: {"a": 1}\n\n'
  assert ts.format_heartbeat("v2").startswith("event: heartbeat")
  assert json.loads(ts.format_heartbeat("v1")[5:])["event"] == "heartbeat"


@pytest.mark.asyncio
async def test_finished_initial_state_ends_immediately(jobs):
  out = await _collect(ts.progress_events("j-fin", {"stage": "failed", "seq": 1}))
  assert len(out) == 1 and '"failed"' in out[0]


@pytest.mark.asyncio
async def test_stale_state_when_not_running(jobs):
  jobs.running = False
  jobs.snap = {"stage": "transcribing", "seq": 2}
  out = await _collect(ts.progress_events("j-stale", {"stage": "queued"}, "v2"))
  assert out == [ts.format_event({"stage": "transcribing", "seq": 2}, "v2")]


@pytest.mark.asyncio
async def test_updates_dedup_and_finish(jobs, monkeypatch):
  queue: asyncio.Queue = asyncio.Queue()
  for u in ({"stage": "transcribing", "seq": 1}, {"stage": "transcribing", "seq": 3},
            {"stage": "transcribing", "seq": 0}, {"stage": "failed", "seq": 5}):
    queue.put_nowait(u)
  monkeypatch.setattr(ts.progress, "subscribe", lambda jid: queue)
  unsub = []
  monkeypatch.setattr(ts.progress, "unsubscribe", lambda jid, q: unsub.append(jid))
  out = await _collect(ts.progress_events("j-up", {"stage": "queued", "seq": 2}))
  seqs = [json.loads(x[5:])["seq"] for x in out]
  assert seqs == [2, 3, 0, 5]  # seq 1 <= last seen is dropped
  assert unsub == ["j-up"]


@pytest.mark.asyncio
async def test_heartbeat_then_final_snapshot(jobs, monkeypatch):
  monkeypatch.setattr(ts, "HEARTBEAT_S", 0.01)
  jobs.running = [True, True, False]
  calls = {"n": 0}

  def latest(jid):
    calls["n"] += 1
    return None if calls["n"] == 1 else {"stage": "complete", "seq": 9}

  monkeypatch.setattr(ts.progress, "latest", latest)
  out = await _collect(ts.progress_events("j-hb", {"stage": "queued", "seq": 1}, "v2"))
  assert out[0].startswith("id: 1")
  assert out.count(ts.format_heartbeat("v2")) == 2
  assert out[-1].startswith("id: 9")


@pytest.mark.asyncio
async def test_heartbeat_no_newer_final(jobs, monkeypatch):
  monkeypatch.setattr(ts, "HEARTBEAT_S", 0.01)
  jobs.running = [True, False]
  out = await _collect(ts.progress_events("j-hb2", {"stage": "queued", "seq": 1}))
  assert out[-1] == ts.format_heartbeat("v1")


def test_endpoint_v1_v2_and_404(monkeypatch, jobs):
  jobs.running = False

  async def get_record(tid):
    return {"id": tid, "user_id": USER_ID} if tid == "mine" else None

  monkeypatch.setattr(tr.records, "get_record", get_record)
  monkeypatch.setattr(tr.records, "can_access", lambda r, u: True)
  import app.features.transcription.service as svc

  monkeypatch.setattr(svc, "job_status", lambda rec: {"id": rec["id"], "stage": "queued", "seq": 7})
  app = FastAPI()
  app.include_router(ts.router, prefix="/api")
  c = TestClient(app, base_url="https://testserver")
  r = c.get("/api/transcription/progress-stream/mine?protocol=v2", headers={"Last-Event-ID": "3"})
  assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
  assert r.text.startswith("id: 7\nevent: progress")
  r = c.get("/api/transcription/progress-stream/mine")
  assert r.text.startswith("data: ")
  assert c.get("/api/transcription/progress-stream/nope").status_code == 404
