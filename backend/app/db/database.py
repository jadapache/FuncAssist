"""Async SQLite Database Connection and Schema Initialization."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
from app.core.settings import USER_DATA_DIR, ensure_local_dirs

def get_db_path() -> Path:
    ensure_local_dirs()
    return USER_DATA_DIR / "app.db"


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.execute("PRAGMA journal_mode = WAL;")
        await db.execute("PRAGMA synchronous = NORMAL;")
        yield db


async def init_db() -> None:
    """Initialize database tables and run lightweight migrations."""
    ensure_local_dirs()
    async with get_db() as db:
        # Users table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                full_name TEXT,
                role TEXT DEFAULT 'user',
                password_hash TEXT,
                password_salt TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Chat history table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                context_sources_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id);
        """)

        # Standups history table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS standups (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                sources_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # PRD reviews history table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS prd_reviews (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                prd_title TEXT NOT NULL,
                content TEXT NOT NULL,
                score INTEGER DEFAULT 0,
                risk_level TEXT DEFAULT 'MEDIUM',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Test plans history table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS test_plans (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                feature_name TEXT NOT NULL,
                test_type TEXT DEFAULT 'regression',
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await db.commit()
