"""Prueba arquitectónica para garantizar el cumplimiento del Repository Pattern.

Reglas:
- Ningún router ni servicio fuera de `backend/app/db/` debe importar directamente modelos ORM (`app.db.models`).
- Ningún router en `backend/app/api/` debe usar directamente sesiones o context managers de `get_db`.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_DIR = BACKEND_DIR / "app"
API_DIR = APP_DIR / "api"


def test_no_orm_models_imported_outside_db():
  """Verifica que ningún archivo fuera de db/ (y de scripts controlados de migración) importe de app.db.models."""
  allowed_files = {
    APP_DIR / "core" / "storage.py",
    APP_DIR / "core" / "integration_migration.py",
  }

  violations = []
  for py_path in APP_DIR.rglob("*.py"):
    if "db" in py_path.parts:
      continue
    if py_path in allowed_files:
      continue

    content = py_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(content)
    for node in ast.walk(tree):
      if isinstance(node, ast.ImportFrom):
        if node.module == "app.db.models":
          violations.append(f"{py_path.relative_to(BACKEND_DIR)}: imports app.db.models")

  assert not violations, f"Violaciones de frontera arquitectónica encontradas: {violations}"


def test_no_get_db_called_in_routers():
  """Verifica que ningún router en app/api/ acceda a get_db() directamente, salvo en deps.py para inyección."""
  violations = []
  for py_path in API_DIR.rglob("*.py"):
    if py_path.name == "deps.py":
      continue
    content = py_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(content)
    for node in ast.walk(tree):
      if isinstance(node, ast.ImportFrom) and node.module == "app.db.database":
        for alias in node.names:
          if alias.name in ("get_db", "get_sync_db"):
            violations.append(f"{py_path.relative_to(BACKEND_DIR)} imports {alias.name}")

  assert not violations, f"Routers llamando a get_db encontrados: {violations}"
