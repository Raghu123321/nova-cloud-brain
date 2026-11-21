import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional, Union
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("nova.brain.engine")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

LOCAL_MEM_DB = Path(__file__).resolve().parent.parent / "nova_local_memories.db"


class LocalMemoryStore:
    """Local SQLite memory store fallback when Supabase / OpenAI keys are not yet configured."""

    def __init__(self, db_path: Path = LOCAL_MEM_DB):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS local_memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    agent_id TEXT,
                    memory TEXT NOT NULL,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def add(self, message: Union[str, List[Dict[str, str]]], user_id: str, agent_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        text_content = ""
        if isinstance(message, str):
            text_content = message.strip()
        elif isinstance(message, list):
            turns = [m.get("content", "") for m in message if isinstance(m, dict)]
            text_content = " | ".join(filter(None, turns))

        if not text_content:
            return []

        mem_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        meta_str = json.dumps(metadata or {})

        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO local_memories (id, user_id, agent_id, memory, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (mem_id, user_id, agent_id, text_content, meta_str, now))
            conn.commit()

        return [{"id": mem_id, "memory": text_content, "event": "ADD"}]

    def search(self, query: str, filters: Dict[str, Any], top_k: int = 3) -> Dict[str, Any]:
        user_id = filters.get("user_id")
        agent_id = filters.get("agent_id")
        terms = [t.lower() for t in query.split() if len(t) > 2]

        with self._get_conn() as conn:
            if agent_id:
                cur = conn.execute("SELECT * FROM local_memories WHERE user_id = ? AND agent_id = ? ORDER BY created_at DESC", (user_id, agent_id))
            else:
                cur = conn.execute("SELECT * FROM local_memories WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
            rows = [dict(r) for r in cur.fetchall()]

        # Rank by keyword overlap
        def score(row):
            txt = row["memory"].lower()
            return sum(1 for term in terms if term in txt)

        ranked = sorted(rows, key=score, reverse=True) if terms else rows
        top_items = ranked[:top_k]
        return {"results": [{"id": r["id"], "memory": r["memory"], "created_at": r["created_at"]} for r in top_items]}

    def get_all(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        user_id = filters.get("user_id")
        agent_id = filters.get("agent_id")
        with self._get_conn() as conn:
            if agent_id:
                cur = conn.execute("SELECT * FROM local_memories WHERE user_id = ? AND agent_id = ? ORDER BY created_at DESC", (user_id, agent_id))
            else:
                cur = conn.execute("SELECT * FROM local_memories WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
            rows = [dict(r) for r in cur.fetchall()]
        return {"results": [{"id": r["id"], "memory": r["memory"], "created_at": r["created_at"]} for r in rows]}

    def delete(self, memory_id: str) -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM local_memories WHERE id = ?", (memory_id,))
            conn.commit()
        return True

    def delete_all(self, user_id: str) -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM local_memories WHERE user_id = ?", (user_id,))
            conn.commit()
        return True


class MemoryEngine:
    """
    Enterprise-grade MaaS Engine wrapping Mem0 with Supabase pgvector.
    Gracefully falls back to local SQLite memory store when cloud credentials are not yet configured.
    """

    def __init__(self):
        self._memory = None
        self._local_store: Optional[LocalMemoryStore] = None
        self._is_local_mode: bool = False
        self.startup_time = time.time()
        self.collection_name = os.getenv("COLLECTION_NAME", "nova_memories")

    def _is_placeholder(self, val: Optional[str]) -> bool:
        if not val:
            return True
        v = val.lower()
        return "yourprojectref" in v or "yourpassword" in v or "your-openai-api-key" in v or "change_this" in v

    def _init_memory(self):
        if self._memory is not None:
            return self._memory

        db_url = os.getenv("SUPABASE_DB_URL", "")
        openai_key = os.getenv("OPENAI_API_KEY", "")

        # Check if cloud credentials are placeholder/missing
        if self._is_placeholder(db_url) or self._is_placeholder(openai_key):
            logger.info("[*] Cloud Supabase/OpenAI credentials not configured. Initializing Local Storage Mode (SQLite).")
            self._is_local_mode = True
            self._local_store = LocalMemoryStore()
            self._memory = self._local_store
            return self._memory

        # Attempt Mem0 + Supabase pgvector initialization
        try:
            from mem0 import Memory
            logger.info(f"Connecting MaaS to Supabase pgvector on collection '{self.collection_name}'...")
            config: Dict[str, Any] = {
                "vector_store": {
                    "provider": "pgvector",
                    "config": {
                        "connection_string": db_url,
                        "collection_name": self.collection_name,
                        "embedding_model_dims": 1536,
                        "sslmode": "require",
                        "hnsw": True,
                    }
                },
                "llm": {
                    "provider": "openai",
                    "config": {
                        "model": "gpt-4o-mini",
                        "api_key": openai_key,
                        "temperature": 0.1,
                    }
                },
                "embedder": {
                    "provider": "openai",
                    "config": {
                        "model": "text-embedding-3-small",
                        "api_key": openai_key,
                    }
                }
            }
            self._memory = Memory.from_config(config)
            self._is_local_mode = False
            logger.info("NOVA MaaS Engine connected to Supabase pgvector successfully!")
            return self._memory
        except Exception as e:
            logger.warning(f"Could not connect to Supabase pgvector ({e}). Falling back to Local Storage Mode (SQLite).")
            self._is_local_mode = True
            self._local_store = LocalMemoryStore()
            self._memory = self._local_store
            return self._memory

    @property
    def client(self):
        if self._memory is None:
            return self._init_memory()
        return self._memory

    def recall(
        self,
        query: str,
        user_id: str = "master_user",
        agent_id: Optional[str] = None,
        top_k: int = 3
    ) -> Dict[str, Any]:
        """Multi-signal hybrid semantic retrieval."""
        filters = {"user_id": user_id}
        if agent_id:
            filters["agent_id"] = agent_id

        results = self.client.search(query=query, filters=filters, top_k=top_k)
        items = results.get("results", [])
        memories = [item.get("memory", "") for item in items if item.get("memory")]
        return {
            "query": query,
            "memories": memories,
            "count": len(memories),
            "raw": items
        }

    def learn(
        self,
        message: Union[str, List[Dict[str, str]]],
        user_id: str = "master_user",
        agent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Extract and persist facts into long-term memory."""
        logger.info(f"Persisting facts for user '{user_id}'...")
        kwargs: Dict[str, Any] = {"user_id": user_id, "metadata": metadata}
        if agent_id:
            kwargs["agent_id"] = agent_id

        res = self.client.add(message, **kwargs)
        logger.info(f"Memory persistence completed: {res}")
        return res

    def get_all(self, user_id: str = "master_user", agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all memories scoped by user and optional agent/device."""
        filters = {"user_id": user_id}
        if agent_id:
            filters["agent_id"] = agent_id

        res = self.client.get_all(filters=filters)
        return res.get("results", [])

    def delete(self, memory_id: str) -> bool:
        """Delete a specific memory by ID."""
        self.client.delete(memory_id=memory_id)
        return True

    def delete_all(self, user_id: str = "master_user") -> bool:
        """Wipe all memories for a user (1-Click Reset)."""
        logger.warning(f"Resetting all memories for user '{user_id}'...")
        self.client.delete_all(user_id=user_id)
        return True

    def get_profile(self, user_id: str = "master_user") -> Dict[str, Any]:
        """Synthesize all memories into a coherent user profile."""
        all_mems = self.get_all(user_id=user_id)
        facts = [m.get("memory", "") for m in all_mems if m.get("memory")]

        if not facts:
            summary = "No profile data stored yet. The assistant will learn your preferences automatically."
        else:
            summary = f"Profile for '{user_id}' built from {len(facts)} synthesized facts."

        return {
            "user_id": user_id,
            "total_facts": len(facts),
            "summary": summary,
            "facts": facts
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return infrastructure health and telemetry."""
        uptime = round(time.time() - self.startup_time, 2)
        total_mems = 0
        try:
            mems = self.get_all(user_id="master_user")
            total_mems = len(mems)
        except Exception:
            pass

        provider_name = "Local SQLite Mode (Configure SUPABASE_DB_URL in .env to connect Cloud pgvector)" if self._is_local_mode else "Supabase pgvector (PostgreSQL)"

        return {
            "status": "healthy",
            "total_memories": total_mems,
            "collection": self.collection_name,
            "db_provider": provider_name,
            "uptime_seconds": uptime,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def export_memories(self, user_id: str = "master_user") -> Dict[str, Any]:
        """Export all user memories as JSON backup."""
        all_mems = self.get_all(user_id=user_id)
        return {
            "user_id": user_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "count": len(all_mems),
            "memories": all_mems
        }

    def import_memories(self, user_id: str, memories_list: List[str]) -> int:
        """Import a batch of memories/facts for a user."""
        count = 0
        for item in memories_list:
            if isinstance(item, str) and item.strip():
                self.client.add(item.strip(), user_id=user_id)
                count += 1
        return count


# Global singleton instance
engine = MemoryEngine()
