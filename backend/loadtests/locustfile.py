"""Pruebas de carga del backend de FuncAssist (Locust).

Uso rápido (desde backend/):
    pip install -r requirements-dev.txt
    export LOAD_USERNAME=... LOAD_PASSWORD=...
    locust -f loadtests/locustfile.py --host https://localhost:8000

Modo sin interfaz (CI / reporte):
    locust -f loadtests/locustfile.py --host https://localhost:8000 \
        --headless -u 50 -r 5 -t 5m --csv reports/load --html reports/load.html

Escenarios:
  * AnonymousUser   -> health checks (sin autenticación).
  * AuthenticatedUser -> login con cookie de sesión y lectura de endpoints
    habituales (perfil, preferencias, historial, borradores, conocimiento).

Los endpoints que invocan a proveedores LLM (document agent, features PM/QA,
resúmenes de transcripción) NO se incluyen: generan coste real y miden la
latencia del proveedor, no la del backend.

Umbrales (SLO) evaluados al finalizar, configurables por entorno:
  LOAD_MAX_FAIL_RATIO (por defecto 0.01)  -> % máximo de peticiones fallidas
  LOAD_MAX_P95_MS     (por defecto 800)   -> percentil 95 agregado en ms
Si se superan, el proceso termina con código 1 (útil en pipelines).
"""

from __future__ import annotations

import os

from locust import HttpUser, between, events, tag, task

USERNAME = os.getenv("LOAD_USERNAME", "")
PASSWORD = os.getenv("LOAD_PASSWORD", "")
VERIFY_TLS = os.getenv("LOAD_VERIFY_TLS", "1") == "1"
MAX_FAIL_RATIO = float(os.getenv("LOAD_MAX_FAIL_RATIO", "0.01"))
MAX_P95_MS = float(os.getenv("LOAD_MAX_P95_MS", "800"))

KNOWLEDGE_QUERIES = [
  "requisitos funcionales",
  "flujo de aprobación",
  "criterios de aceptación",
  "integración con Jira",
  "plan de pruebas",
]


class AnonymousUser(HttpUser):
  """Tráfico de sondas / balanceador: solo health checks."""

  weight = 1
  wait_time = between(1, 3)

  def on_start(self) -> None:
    self.client.verify = VERIFY_TLS

  @tag("health")
  @task(3)
  def health(self) -> None:
    self.client.get("/api/health", name="GET /api/health")

  @tag("health")
  @task(1)
  def ready(self) -> None:
    self.client.get("/api/health/ready", name="GET /api/health/ready")


class AuthenticatedUser(HttpUser):
  """Usuario aprobado navegando la aplicación."""

  weight = 4
  wait_time = between(1, 5)

  def on_start(self) -> None:
    self.client.verify = VERIFY_TLS
    if not USERNAME or not PASSWORD:
      raise RuntimeError(
        "Defina LOAD_USERNAME y LOAD_PASSWORD con un usuario aprobado (no admin de producción)."
      )
    with self.client.post(
      "/api/auth/login",
      json={"username": USERNAME, "password": PASSWORD},
      name="POST /api/auth/login",
      catch_response=True,
    ) as resp:
      if resp.status_code != 200 or "funcassist_session" not in self.client.cookies:
        resp.failure(f"login falló: {resp.status_code} {resp.text[:200]}")
      else:
        resp.success()

  def on_stop(self) -> None:
    self.client.post("/api/auth/logout", name="POST /api/auth/logout")

  @tag("auth")
  @task(5)
  def me(self) -> None:
    self.client.get("/api/auth/me", name="GET /api/auth/me")

  @tag("profile")
  @task(3)
  def profile(self) -> None:
    self.client.get("/api/user/profile", name="GET /api/user/profile")

  @tag("profile")
  @task(2)
  def preferences(self) -> None:
    self.client.get("/api/me/preferences", name="GET /api/me/preferences")

  @tag("history")
  @task(4)
  def chat_sessions(self) -> None:
    self.client.get("/api/chat/sessions", name="GET /api/chat/sessions")

  @tag("history")
  @task(2)
  def standups(self) -> None:
    self.client.get("/api/history/standups", name="GET /api/history/standups")

  @tag("history")
  @task(2)
  def prd_reviews(self) -> None:
    self.client.get("/api/history/prd-reviews", name="GET /api/history/prd-reviews")

  @tag("knowledge")
  @task(2)
  def knowledge_documents(self) -> None:
    self.client.get("/api/knowledge/documents", name="GET /api/knowledge/documents")

  @tag("knowledge")
  @task(3)
  def knowledge_retrieve(self) -> None:
    query = KNOWLEDGE_QUERIES[id(self) % len(KNOWLEDGE_QUERIES)]
    self.client.post(
      "/api/knowledge/retrieve",
      json={"query": query, "top_k": 5},
      name="POST /api/knowledge/retrieve",
    )


@events.quitting.add_listener
def enforce_slo(environment, **_kwargs) -> None:
  stats = environment.stats.total
  if stats.num_requests == 0:
    return
  p95 = stats.get_response_time_percentile(0.95)
  fail_ratio = stats.fail_ratio
  problems = []
  if fail_ratio > MAX_FAIL_RATIO:
    problems.append(f"fail_ratio={fail_ratio:.2%} > {MAX_FAIL_RATIO:.2%}")
  if p95 > MAX_P95_MS:
    problems.append(f"p95={p95:.0f}ms > {MAX_P95_MS:.0f}ms")
  if problems:
    print("SLO incumplido: " + "; ".join(problems))
    environment.process_exit_code = 1
  else:
    print(f"SLO OK: p95={p95:.0f}ms, fail_ratio={fail_ratio:.2%}")
