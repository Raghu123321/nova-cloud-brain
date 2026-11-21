import hashlib
import logging
import os
from pathlib import Path
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nova.brain.db")

DB_FILE = Path(__file__).resolve().parent.parent / "nova_brain_auth.db"
SALT = "nova_brain_auth_salt_2026_xyz"


class DatabaseManager:
    """
    Unified database manager for Users, Authentication, API Keys, and Usage Telemetry.
    Supports Admin & Multi-User Accounts with Password & API Key Authentication.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_FILE
        self._init_schema()
        self._seed_admin_account()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _hash_password(self, password: str) -> str:
        """One-way salted cryptographic hash for user passwords."""
        return hashlib.sha256(f"{SALT}_{password.strip()}".encode("utf-8")).hexdigest()

    def _hash_key(self, raw_key: str) -> str:
        """One-way SHA-256 cryptographic hash for API keys."""
        return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()

    def _init_schema(self):
        """Creates tables for users, api_keys, and usage telemetry audit logs."""
        with self._get_connection() as conn:
            # 1. Users Table (with salted password_hash)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL
                )
            """)

            # 2. API Keys Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    key_hash TEXT UNIQUE NOT NULL,
                    raw_key TEXT,
                    key_prefix TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT 'Default Key',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            # 3. Usage & Audit Logs Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    details TEXT
                )
            """)
            conn.commit()
            logger.info("Database schema initialized successfully.")

    def _seed_admin_account(self):
        """Ensures the Master Admin account exists with configured credentials."""
        admin_u = os.getenv("ADMIN_USERNAME", "admin").strip()
        admin_p = os.getenv("ADMIN_PASSWORD", "admin123").strip()
        admin_hash = self._hash_password(admin_p)
        now = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cur = conn.execute("SELECT id FROM users WHERE role = 'admin' OR email = 'admin@novabrain.local' OR id = 'admin_master'")
            admin_row = cur.fetchone()
            if not admin_row:
                admin_id = "admin_master"
                conn.execute("""
                    INSERT INTO users (id, name, email, password_hash, role, status, created_at)
                    VALUES (?, 'System Administrator', 'admin@novabrain.local', ?, 'admin', 'active', ?)
                """, (admin_id, admin_hash, now))

                # Admin master API key
                env_key = os.getenv("BRAIN_API_KEY", "").strip()
                if not env_key or "change_this" in env_key:
                    env_key = f"nb_live_{secrets.token_hex(20)}"
                    os.environ["BRAIN_API_KEY"] = env_key

                key_hash = self._hash_key(env_key)
                prefix = f"{env_key[:10]}...{env_key[-4:]}"
                key_id = f"key_{secrets.token_hex(8)}"

                conn.execute("""
                    INSERT INTO api_keys (id, user_id, key_hash, raw_key, key_prefix, name, is_active, created_at, last_used_at)
                    VALUES (?, ?, ?, ?, ?, 'Admin Master Key', 1, ?, ?)
                """, (key_id, admin_id, key_hash, env_key, prefix, now, now))
                conn.commit()
                logger.info(f"Seeded Master Admin account '{admin_u}' with key prefix '{prefix}'.")
            else:
                # Update admin password hash if changed in environment
                conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (admin_hash, admin_row["id"]))
                conn.commit()

    # ============================================================
    # Authentication & User Operations
    # ============================================================

    def signup_user(self, name: str, email: str, password: str) -> Tuple[Dict[str, Any], str]:
        """Registers a new user, hashes password, and issues their first unique API key."""
        clean_name = name.strip()
        clean_email = email.strip().lower()
        if not clean_email or not password or not clean_name:
            raise ValueError("Name, email, and password are all required.")

        with self._get_connection() as conn:
            cur = conn.execute("SELECT id FROM users WHERE email = ?", (clean_email,))
            if cur.fetchone():
                raise ValueError(f"An account with email '{clean_email}' already exists. Please sign in.")

            user_id = f"usr_{secrets.token_hex(8)}"
            now = datetime.now(timezone.utc).isoformat()
            pass_hash = self._hash_password(password)

            conn.execute("""
                INSERT INTO users (id, name, email, password_hash, role, status, created_at)
                VALUES (?, ?, ?, ?, 'user', 'active', ?)
            """, (user_id, clean_name, clean_email, pass_hash, now))

            # Generate first API key for this user
            raw_key = f"nb_live_{secrets.token_hex(20)}"
            key_hash = self._hash_key(raw_key)
            prefix = f"{raw_key[:10]}...{raw_key[-4:]}"
            key_id = f"key_{secrets.token_hex(8)}"

            conn.execute("""
                INSERT INTO api_keys (id, user_id, key_hash, raw_key, key_prefix, name, is_active, created_at, last_used_at)
                VALUES (?, ?, ?, ?, ?, 'Primary Key', 1, ?, ?)
            """, (key_id, user_id, key_hash, raw_key, prefix, now, now))
            conn.commit()

        user_data = self.get_user(user_id)
        return user_data, raw_key

    def create_user(
        self,
        name: str,
        email: str,
        role: str = "user",
        password: Optional[str] = None
    ) -> Tuple[Dict[str, Any], str]:
        """Admin helper to provision a user with an auto-generated password if omitted."""
        pwd = password or f"User@{secrets.token_hex(4)}"
        clean_email = email.strip().lower()
        clean_name = name.strip()

        with self._get_connection() as conn:
            cur = conn.execute("SELECT id FROM users WHERE email = ?", (clean_email,))
            if cur.fetchone():
                raise ValueError(f"An account with email '{clean_email}' already exists.")

            user_id = f"usr_{secrets.token_hex(8)}"
            now = datetime.now(timezone.utc).isoformat()
            pass_hash = self._hash_password(pwd)

            conn.execute("""
                INSERT INTO users (id, name, email, password_hash, role, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'active', ?)
            """, (user_id, clean_name, clean_email, pass_hash, role, now))

            raw_key = f"nb_live_{secrets.token_hex(20)}"
            key_hash = self._hash_key(raw_key)
            prefix = f"{raw_key[:10]}...{raw_key[-4:]}"
            key_id = f"key_{secrets.token_hex(8)}"

            conn.execute("""
                INSERT INTO api_keys (id, user_id, key_hash, raw_key, key_prefix, name, is_active, created_at, last_used_at)
                VALUES (?, ?, ?, ?, ?, 'Provisioned Key', 1, ?, ?)
            """, (key_id, user_id, key_hash, raw_key, prefix, now, now))
            conn.commit()

        user_data = self.get_user(user_id)
        return user_data, raw_key

    def authenticate_user(self, identifier: str, password: str) -> Optional[Tuple[Dict[str, Any], str]]:
        """
        Validates user or admin credentials.
        Returns (user_dict, active_api_key) if valid; otherwise None.
        """
        clean_id = identifier.strip().lower()
        admin_u = os.getenv("ADMIN_USERNAME", "admin").strip().lower()
        admin_p = os.getenv("ADMIN_PASSWORD", "admin123").strip()

        # 1. Admin login check
        if clean_id in (admin_u, "admin@novabrain.local", "admin"):
            if secrets.compare_digest(password.strip(), admin_p):
                admin_user = self.get_user("admin_master") or {
                    "id": "admin_master",
                    "name": "System Administrator",
                    "email": "admin@novabrain.local",
                    "role": "admin",
                    "status": "active",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                admin_key = self.get_active_key_for_user(admin_user["id"])
                return admin_user, admin_key

        # 2. Regular user authentication by email, name, or username prefix
        pass_hash = self._hash_password(password)
        id_no_spaces = clean_id.replace(" ", "")

        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT id, name, email, role, status, created_at
                FROM users 
                WHERE (
                    LOWER(email) = ? 
                    OR LOWER(name) = ? 
                    OR LOWER(REPLACE(name, ' ', '')) = ?
                    OR LOWER(SUBSTR(email, 1, INSTR(email, '@') - 1)) = ?
                    OR LOWER(id) = ?
                ) AND password_hash = ?
            """, (clean_id, clean_id, id_no_spaces, clean_id, clean_id, pass_hash))
            row = cur.fetchone()
            if not row:
                return None

            user_data = dict(row)
            if user_data.get("status") != "active":
                raise ValueError("Account is suspended. Please contact the administrator.")

            api_key = self.get_active_key_for_user(user_data["id"])
            return user_data, api_key

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT id, name, email, role, status, created_at FROM users WHERE id = ?", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT id, name, email, role, status, created_at FROM users WHERE email = ?", (email.strip().lower(),))
            row = cur.fetchone()
            return dict(row) if row else None

    def list_users(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT id, name, email, role, status, created_at FROM users ORDER BY created_at DESC")
            return [dict(r) for r in cur.fetchall()]

    def update_user_status(self, user_id: str, status: str) -> bool:
        with self._get_connection() as conn:
            conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
            conn.commit()
            return True

    def delete_user(self, user_id: str) -> bool:
        """Permanently removes a user and cascades deletion of their keys and logs."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.execute("DELETE FROM api_keys WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM usage_logs WHERE user_id = ?", (user_id,))
            conn.commit()
            return True

    # ============================================================
    # API Key Operations
    # ============================================================

    def get_active_key_for_user(self, user_id: str) -> str:
        """Returns the user's active raw API key, or generates a fresh one."""
        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT raw_key, key_prefix FROM api_keys
                WHERE user_id = ? AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
            """, (user_id,))
            row = cur.fetchone()
            if row:
                if row["raw_key"]:
                    return row["raw_key"]
                return row["key_prefix"]

        # Create fresh key if user had no active key
        raw_key, _ = self.create_api_key(user_id=user_id, name="Default Key")
        return raw_key

    def create_api_key(self, user_id: str, name: str = "Client Device") -> Tuple[str, Dict[str, Any]]:
        """Generates a new API key for a user. Returns (raw_key, key_record)."""
        raw_key = f"nb_live_{secrets.token_hex(20)}"
        key_hash = self._hash_key(raw_key)
        prefix = f"{raw_key[:10]}...{raw_key[-4:]}"
        key_id = f"key_{secrets.token_hex(8)}"
        now = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO api_keys (id, user_id, key_hash, raw_key, key_prefix, name, is_active, created_at, last_used_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (key_id, user_id, key_hash, raw_key, prefix, name, now, now))
            conn.commit()

        key_record = {
            "id": key_id,
            "user_id": user_id,
            "key_prefix": prefix,
            "name": name,
            "is_active": True,
            "created_at": now
        }
        return raw_key, key_record

    def verify_key_and_get_user(self, raw_key: str) -> Optional[Dict[str, Any]]:
        """
        Verifies raw API key against stored SHA-256 hashes or raw keys.
        Returns user dictionary if active; otherwise None.
        Updates last_used_at timestamp.
        """
        clean_key = raw_key.strip()
        key_hash = self._hash_key(clean_key)
        now = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT k.id as key_id, k.is_active, u.id, u.name, u.email, u.role, u.status
                FROM api_keys k
                JOIN users u ON k.user_id = u.id
                WHERE (k.key_hash = ? OR k.raw_key = ?)
            """, (key_hash, clean_key))
            row = cur.fetchone()
            if not row:
                return None

            user_data = dict(row)
            if not user_data.get("is_active") or user_data.get("status") != "active":
                return None

            conn.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (now, user_data["key_id"]))
            conn.commit()
            return user_data

    def list_keys_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT id, user_id, key_prefix, name, is_active, created_at, last_used_at
                FROM api_keys WHERE user_id = ? ORDER BY created_at DESC
            """, (user_id,))
            return [dict(r) for r in cur.fetchall()]

    def revoke_key(self, key_id: str) -> bool:
        with self._get_connection() as conn:
            conn.execute("UPDATE api_keys SET is_active = 0 WHERE id = ?", (key_id,))
            conn.commit()
            return True

    # ============================================================
    # Usage & Audit Telemetry Logs
    # ============================================================

    def log_usage(
        self,
        user_id: str,
        endpoint: str,
        method: str,
        status_code: int,
        latency_ms: float,
        details: str = ""
    ):
        """Records an immutable audit trace of every single API request."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO usage_logs (user_id, endpoint, method, status_code, latency_ms, timestamp, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, endpoint, method, status_code, round(latency_ms, 2), now, details[:500]))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log usage telemetry: {e}")

    def get_user_metrics(self, user_id: str) -> Dict[str, Any]:
        """Calculates total requests, last active timestamp, and endpoint breakdown."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT COUNT(*), MAX(timestamp) FROM usage_logs WHERE user_id = ?", (user_id,))
            count, last_active = cur.fetchone()

            cur_ep = conn.execute("""
                SELECT endpoint, COUNT(*) as req_count
                FROM usage_logs WHERE user_id = ?
                GROUP BY endpoint
            """, (user_id,))
            breakdown = {r["endpoint"]: r["req_count"] for r in cur_ep.fetchall()}

            return {
                "total_requests": count or 0,
                "last_active": last_active or "Never",
                "endpoint_breakdown": breakdown
            }

    def get_all_usage_logs(self, limit: int = 100, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Admin audit trace: Returns recent request logs with filtering."""
        with self._get_connection() as conn:
            if user_id:
                cur = conn.execute("""
                    SELECT * FROM usage_logs WHERE user_id = ?
                    ORDER BY id DESC LIMIT ?
                """, (user_id, limit))
            else:
                cur = conn.execute("""
                    SELECT * FROM usage_logs
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    def get_admin_dashboard_metrics(self) -> Dict[str, Any]:
        """Global metrics for Admin Dashboard."""
        with self._get_connection() as conn:
            total_users = conn.execute("SELECT COUNT(*) FROM users WHERE role != 'admin'").fetchone()[0]
            total_keys = conn.execute("SELECT COUNT(*) FROM api_keys WHERE is_active = 1").fetchone()[0]
            total_requests = conn.execute("SELECT COUNT(*) FROM usage_logs").fetchone()[0]
            avg_latency = conn.execute("SELECT AVG(latency_ms) FROM usage_logs").fetchone()[0] or 0

            return {
                "total_users": total_users,
                "active_keys": total_keys,
                "total_requests": total_requests,
                "avg_latency_ms": round(avg_latency, 2)
            }


# Global database manager instance
db = DatabaseManager()
