from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from app.db.database import get_db
from app.db.interfaces.user_repository import IUserRepository


class UserRepository(IUserRepository):
    """Implementación SQLite asíncrona de IUserRepository."""

    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        async with get_db() as db:
            async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None

    async def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        async with get_db() as db:
            async with db.execute("SELECT * FROM users WHERE username = ?", (username,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
        return None

    async def count(self) -> int:
        async with get_db() as db:
            async with db.execute("SELECT COUNT(*) as count FROM users") as cursor:
                row = await cursor.fetchone()
                return int(row["count"]) if row else 0

    async def create_user_with_password(
        self,
        username: str,
        password_hash: str,
        password_salt: str,
        email: str = "",
        full_name: str = "",
        role: str = "user",
        status: str = "pending",
    ) -> Dict[str, Any]:
        user_id = str(uuid.uuid4())
        total_users = await self.count()

        # Bootstrap: El primer usuario registrado es automáticamente admin y approved
        final_status = "approved" if total_users == 0 else status
        final_role = "admin" if total_users == 0 else role

        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO users (id, username, email, full_name, role, password_hash, password_salt, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    email,
                    full_name or username,
                    final_role,
                    password_hash,
                    password_salt,
                    final_status,
                ),
            )
            await db.commit()

        user = await self.get_by_id(user_id)
        return user or {
            "id": user_id,
            "username": username,
            "email": email,
            "full_name": full_name or username,
            "role": final_role,
            "status": final_status,
        }

    async def get_pending_users(self) -> List[Dict[str, Any]]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM users WHERE status = 'pending' ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def update_user_status(self, user_id: str, status: str) -> Optional[Dict[str, Any]]:
        async with get_db() as db:
            await db.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
            await db.commit()
        return await self.get_by_id(user_id)

    async def update(self, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not updates:
            return await self.get_by_id(user_id)

        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = tuple(updates.values()) + (user_id,)
        async with get_db() as db:
            await db.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
            await db.commit()
        return await self.get_by_id(user_id)

    async def delete(self, user_id: str) -> bool:
        async with get_db() as db:
            cursor = await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            await db.commit()
            return cursor.rowcount > 0
