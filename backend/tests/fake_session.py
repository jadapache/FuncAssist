"""In-memory SQLAlchemy Fake Sessions for testing PostgreSQL ORM queries.

Zero SQLite dependencies - operates strictly as an in-memory double of SQLAlchemy AsyncSession/Session.
"""

from __future__ import annotations

import copy
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Dict, Generator, List, Optional, Type

from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList


def _eval_clause(clause: Any, obj: Any) -> bool:
  if clause is None:
    return True

  # Handle Grouping expressions (e.g. ~(Model.field.like(...)))
  if hasattr(clause, "element"):
    return _eval_clause(clause.element, obj)

  # BinaryExpression (e.g. Model.field == value)
  if hasattr(clause, "left") and hasattr(clause, "right"):
    col_name = getattr(clause.left, "key", getattr(clause.left, "name", None))
    val = getattr(clause.right, "value", None)
    if hasattr(val, "value"):
      val = val.value
    obj_val = getattr(obj, col_name, None)
    return obj_val == val

  # BooleanClauseList (and_, or_)
  if hasattr(clause, "clauses"):
    return all(_eval_clause(sub, obj) for sub in clause.clauses)

  return True


class FakeScalars:
  def __init__(self, items: List[Any]):
    self._items = items

  def all(self) -> List[Any]:
    return list(self._items)

  def first(self) -> Any:
    return self._items[0] if self._items else None

  def one_or_none(self) -> Any:
    return self._items[0] if self._items else None


class FakeResult:
  def __init__(self, items: List[Any], is_count: bool = False, count_val: int = 0):
    self._items = items
    self._is_count = is_count
    self._count_val = count_val

  def scalar_one_or_none(self) -> Any:
    return self._items[0] if self._items else None

  def scalar(self) -> Any:
    if self._is_count:
      return self._count_val
    return self._items[0] if self._items else None

  def scalars(self) -> FakeScalars:
    return FakeScalars(self._items)

  def all(self) -> List[Any]:
    return list(self._items)


class FakeStorage:
  def __init__(self):
    self.tables: Dict[Type, Dict[str, Any]] = {}

  def clear(self):
    self.tables.clear()


GLOBAL_FAKE_STORAGE = FakeStorage()


class FakeAsyncSession:
  def __init__(self, storage: Optional[FakeStorage] = None):
    self.storage = storage or GLOBAL_FAKE_STORAGE
    self._take_snapshot()

  def _take_snapshot(self) -> None:
    self._snapshot = {
      model_cls: {k: copy.copy(v) for k, v in table_dict.items()}
      for model_cls, table_dict in self.storage.tables.items()
    }

  async def __aenter__(self):
    return self

  async def __aexit__(self, exc_type, exc_val, exc_tb):
    pass

  def add(self, obj: Any) -> None:
    t = type(obj)
    if t not in self.storage.tables:
      self.storage.tables[t] = {}
    obj_id = getattr(obj, "id", None) or getattr(obj, "key", None) or str(id(obj))
    self.storage.tables[t][obj_id] = obj

  async def commit(self) -> None:
    self._take_snapshot()

  async def rollback(self) -> None:
    self.storage.tables.clear()
    for model_cls, table_dict in self._snapshot.items():
      self.storage.tables[model_cls] = {k: copy.copy(v) for k, v in table_dict.items()}

  async def refresh(self, obj: Any) -> None:
    pass

  async def delete(self, obj: Any) -> None:
    t = type(obj)
    if t in self.storage.tables:
      obj_id = getattr(obj, "id", None) or getattr(obj, "key", None) or str(id(obj))
      self.storage.tables[t].pop(obj_id, None)

  async def execute(self, stmt: Any) -> FakeResult:
    return _eval_statement(stmt, self.storage)

  async def scalars(self, stmt: Any) -> FakeScalars:
    res = await self.execute(stmt)
    return res.scalars()

  async def scalar(self, stmt: Any) -> Any:
    res = await self.execute(stmt)
    return res.scalar()


def _eval_statement(stmt: Any, storage: FakeStorage) -> FakeResult:
  # Handle DELETE statements
  if stmt.__class__.__name__ == "Delete":
    table_name = getattr(stmt.table, "name", None)
    target_type = None
    for model_cls in storage.tables:
      if getattr(model_cls, "__tablename__", None) == table_name:
        target_type = model_cls
        break
    if target_type and target_type in storage.tables:
      to_del = [
        k for k, v in storage.tables[target_type].items()
        if _eval_clause(stmt.whereclause, v)
      ]
      for k in to_del:
        storage.tables[target_type].pop(k, None)
    return FakeResult([])

  # Handle SELECT statements
  desc = getattr(stmt, "column_descriptions", [])
  if not desc:
    return FakeResult([])

  first = desc[0]
  expr = first.get("expr")
  target_type = first.get("entity") or getattr(expr, "class_", None) or first.get("type")

  is_count = False
  if hasattr(expr, "name") and str(expr.name).lower() == "count":
    is_count = True
    # Find from clause or entity
    froms = list(stmt.get_final_froms())
    if froms:
      table_name = getattr(froms[0], "name", None)
      for model_cls in storage.tables:
        if getattr(model_cls, "__tablename__", None) == table_name:
          target_type = model_cls
          break

  if target_type not in storage.tables:
    storage.tables[target_type] = {}

  all_objs = list(storage.tables[target_type].values())
  col_key = getattr(expr, "key", None) if (expr is not target_type) and hasattr(expr, "class_") else None
  if col_key:
    filtered = [getattr(o, col_key, None) for o in all_objs if _eval_clause(stmt.whereclause, o)]
  else:
    filtered = [o for o in all_objs if _eval_clause(stmt.whereclause, o)]

  # Ordering
  order_clauses = getattr(stmt, "_order_by_clauses", ())
  if order_clauses:
    for oc in order_clauses:
      col = getattr(oc, "element", None)
      if col is None:
        col = oc
      col_name = getattr(col, "key", getattr(col, "name", None))
      is_desc = getattr(oc, "modifier", None) is not None or "desc" in str(oc).lower()
      if col_name:
        filtered.sort(
          key=lambda x: (getattr(x, col_name) is None, getattr(x, col_name)),
          reverse=is_desc,
        )

  # Limit
  limit_clause = getattr(stmt, "_limit_clause", None)
  if limit_clause is not None:
    try:
      lim = int(limit_clause.value)
      filtered = filtered[:lim]
    except Exception:
      pass

  if is_count:
    return FakeResult([], is_count=True, count_val=len(filtered))

  return FakeResult(filtered)


class FakeSyncSession:
  def __init__(self, storage: Optional[FakeStorage] = None):
    self.storage = storage or GLOBAL_FAKE_STORAGE
    self._take_snapshot()

  def _take_snapshot(self) -> None:
    self._snapshot = {
      model_cls: {k: copy.copy(v) for k, v in table_dict.items()}
      for model_cls, table_dict in self.storage.tables.items()
    }

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_val, exc_tb):
    pass

  def add(self, obj: Any) -> None:
    t = type(obj)
    if t not in self.storage.tables:
      self.storage.tables[t] = {}
    obj_id = getattr(obj, "id", None) or getattr(obj, "key", None) or str(id(obj))
    self.storage.tables[t][obj_id] = obj

  def commit(self) -> None:
    self._take_snapshot()

  def rollback(self) -> None:
    self.storage.tables.clear()
    for model_cls, table_dict in self._snapshot.items():
      self.storage.tables[model_cls] = {k: copy.copy(v) for k, v in table_dict.items()}

  def refresh(self, obj: Any) -> None:
    pass

  def delete(self, obj: Any) -> None:
    t = type(obj)
    if t in self.storage.tables:
      obj_id = getattr(obj, "id", None) or getattr(obj, "key", None) or str(id(obj))
      self.storage.tables[t].pop(obj_id, None)

  def execute(self, stmt: Any) -> FakeResult:
    # Synchronous execution sharing evaluation logic
    return _eval_statement(stmt, self.storage)

  def scalars(self, stmt: Any) -> FakeScalars:
    res = self.execute(stmt)
    return res.scalars()

  def scalar(self, stmt: Any) -> Any:
    res = self.execute(stmt)
    return res.scalar()

  def scalar_one_or_none(self, stmt: Any) -> Any:
    res = self.execute(stmt)
    return res.scalar_one_or_none()


@asynccontextmanager
async def fake_async_db():
  yield FakeAsyncSession(GLOBAL_FAKE_STORAGE)


@contextmanager
def fake_sync_db():
  yield FakeSyncSession(GLOBAL_FAKE_STORAGE)
