"""Smoke checks for the LLM layer against the real catalog and, optionally, the real providers.

Without --live it makes no API calls: it shows which main/fast models the catalog resolves to.
With --live, for each provider whose key is configured (user settings or env vars):
  1. fast tier: a short completion, reporting whether the main-model recovery kicked in;
  2. section planning: `plan_document` on a test request (acceptance of plan point 1: sections > 0);
  3. tool calling: `supports_tools()`, then a streamed tool call and a final answer after the tool
     result (plan point 7: agent streaming with accumulated tool-call deltas).

Usage (from backend/, e.g. inside the backend container):
  python -m scripts.smoke_ai_providers
  python -m scripts.smoke_ai_providers --live --providers groq,claude,openai
  python -m scripts.smoke_ai_providers --live --user <user_id>     # use that user's stored keys
Exit code 1 if any live check fails.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Sequence

backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
  sys.path.insert(0, str(backend_root))

DEFAULT_PROVIDERS = ("groq", "claude", "openai", "gemini")
PLAN_REQUEST = "Genera un plan de pruebas para el módulo de inicio de sesión de una aplicación web."
TOOL_SCHEMA = {
  "type": "function",
  "function": {
    "name": "get_server_time",
    "description": "Devuelve la fecha y hora actual del servidor en formato ISO 8601.",
    "parameters": {"type": "object", "properties": {}, "required": []},
  },
}


def _same_model(served: str, configured: str) -> bool:
  """Providers report dated ids (claude-haiku-4-5-20251001) for aliases (claude-haiku-4-5)."""
  a, b = served.split("/")[-1], configured.split("/")[-1]
  return a == b or a.startswith(b) or b.startswith(a)


class Report:
  def __init__(self) -> None:
    self.failures = 0

  def line(self, status: str, provider: str, check: str, detail: str = "") -> None:
    if status == "FAIL":
      self.failures += 1
    print(f"[{status:<4}] {provider:<8} {check:<16} {detail}")


def check_catalog(provider: str, report: Report) -> None:
  from app.ai.catalog import catalog_chat_models, pick_model
  from app.ai.providers.registry import find_provider_spec

  spec = find_provider_spec(provider)
  if spec is None:
    report.line("FAIL", provider, "catalog", "unknown provider")
    return
  available = catalog_chat_models(spec.id)
  main = pick_model(spec.id, "main", spec.default_model)
  fast = pick_model(spec.id, "fast", spec.fast_model)
  report.line("INFO", provider, "catalog", f"{len(available)} chat models; main={main} fast={fast or '(main)'}")
  for label, name in (("registry main", spec.default_model), ("registry fast", spec.fast_model)):
    if available and name not in available:
      report.line("WARN", provider, label, f"{name} is not in the catalog (only used as last resort)")


async def check_live(provider: str, user_id: str | None, report: Report) -> None:
  from app.ai.providers.base import AIMessage
  from app.ai.providers.factory import resolve_provider
  from app.ai.section_generator import plan_document

  try:
    main = resolve_provider(provider_name=provider, user_id=user_id)
    fast = resolve_provider(provider_name=provider, user_id=user_id, tier="fast", main_model=main.default_model)
  except ValueError as exc:
    report.line("SKIP", provider, "live", str(exc))
    return

  # 1. Fast tier
  t0 = time.perf_counter()
  try:
    res = await fast.complete([AIMessage(role="user", content="Responde únicamente: OK")], max_tokens=200)
    recovered = bool(fast.not_found_fallback) and _same_model(res.model, fast.not_found_fallback) \
      and not _same_model(res.model, fast.default_model)
    detail = f"model={res.model} {(time.perf_counter() - t0) * 1000:.0f} ms"
    if recovered:
      detail += f" (configured {fast.default_model} failed, recovered with the main model)"
    report.line("WARN" if recovered else "OK", provider, "fast tier", detail)
  except Exception as exc:
    report.line("FAIL", provider, "fast tier", f"{fast.default_model}: {exc}")

  # 2. Section planning (what decides route=sections)
  try:
    plan = await plan_document(PLAN_REQUEST, "", provider=fast)
    if plan and plan.sections:
      report.line("OK", provider, "section plan", f"{len(plan.sections)} sections: {plan.title}")
    else:
      report.line("FAIL", provider, "section plan", "no valid plan (see warnings above)")
  except Exception as exc:
    report.line("FAIL", provider, "section plan", str(exc))

  # 3. Tool calling with streaming
  if not main.supports_tools():
    report.line("SKIP", provider, "tool calling", f"{main.default_model} has no tool calling; agent mode uses the plain route")
    return
  convo = [
    AIMessage(role="system", content="Eres un asistente. Usa las herramientas disponibles cuando se te pida."),
    AIMessage(role="user", content="¿Qué hora es en el servidor? Usa la herramienta get_server_time."),
  ]
  try:
    sink: dict[str, Any] = {}
    text = "".join([
      chunk async for chunk in main.complete_stream(
        convo, tools=[TOOL_SCHEMA], tool_choice="auto", max_tokens=400, usage_sink=sink,
      )
    ])
    calls = sink.get("tool_calls") or []
    if not calls:
      report.line("FAIL", provider, "tool call", f"no tool call streamed (finish_reason={sink.get('finish_reason')})")
      return
    report.line("OK", provider, "tool call", f"{calls[0].name}({calls[0].arguments}) id={calls[0].id}")

    convo += [
      AIMessage(role="assistant", content=text, tool_calls=calls),
      AIMessage(role="tool", tool_call_id=calls[0].id, content="2026-11-20T22:00:00Z"),
    ]
    final_sink: dict[str, Any] = {}
    final = "".join([
      chunk async for chunk in main.complete_stream(
        convo, tools=[TOOL_SCHEMA], tool_choice="none", max_tokens=400, usage_sink=final_sink,
      )
    ])
    if final.strip():
      report.line("OK", provider, "tool answer", f"{final.strip()[:70]!r} ttft={final_sink.get('ttft_ms')} ms")
    else:
      report.line("FAIL", provider, "tool answer", "empty answer after the tool result")
  except Exception as exc:
    report.line("FAIL", provider, "tool calling", str(exc))


async def run(providers: Sequence[str], live: bool, user_id: str | None) -> int:
  report = Report()
  for provider in providers:
    try:
      check_catalog(provider, report)
    except Exception as exc:
      report.line("FAIL", provider, "catalog", str(exc))
    if live:
      await check_live(provider, user_id, report)
  return report.failures


def main(argv: Sequence[str] | None = None) -> None:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--live", action="store_true", help="Call the providers (uses API credit).")
  parser.add_argument("--providers", default=",".join(DEFAULT_PROVIDERS), help="Comma-separated provider ids.")
  parser.add_argument("--user", help="Use this user's stored AI settings and keys.")
  args = parser.parse_args(argv)
  providers = [p.strip() for p in args.providers.split(",") if p.strip()]
  failures = asyncio.run(run(providers, args.live, args.user))
  sys.exit(1 if failures else 0)


if __name__ == "__main__":
  main()
