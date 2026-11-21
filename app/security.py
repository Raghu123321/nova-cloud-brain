import hashlib
import logging
import os
from pathlib import Path
import secrets
import time
from typing import Any, Dict, Optional
from dotenv import load_dotenv, set_key
from fastapi import Header, HTTPException, status
from app.db import db

logger = logging.getLogger("nova.brain.security")

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

# Admin Credentials (configurable via environment, default: admin / admin123)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123").strip()

# In-memory store for active session tokens: Token -> Dict[str, Any]
_SESSIONS: Dict[str, Dict[str, Any]] = {}
SESSION_TTL_SECONDS = 7 * 86400  # 7 Days


def get_or_generate_api_key() -> str:
    """Returns the master API key from environment or generates a secure default."""
    key = os.getenv("BRAIN_API_KEY", "").strip()
    if not key or "change_this" in key or key == "nova_secret_12345":
        key = f"nb_live_{secrets.token_hex(20)}"
        os.environ["BRAIN_API_KEY"] = key
        try:
            if ENV_PATH.exists():
                set_key(str(ENV_PATH), "BRAIN_API_KEY", key)
        except Exception:
            pass
    return key


def create_user_session(user: Dict[str, Any], api_key: str) -> str:
    """Creates a stateful 7-day session token for web/client authentication."""
    token = f"nb_sess_{secrets.token_hex(24)}"
    _SESSIONS[token] = {
        "user_id": user["id"],
        "user": user,
        "role": user.get("role", "user"),
        "api_key": api_key,
        "expires_at": time.time() + SESSION_TTL_SECONDS
    }
    return token


def invalidate_session(token: str) -> bool:
    """Removes a session token on logout."""
    if token in _SESSIONS:
        del _SESSIONS[token]
        return True
    return False


def get_session_data(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Retrieves active session if token exists and has not expired."""
    if not token or token not in _SESSIONS:
        return None
    session = _SESSIONS[token]
    if time.time() > session["expires_at"]:
        del _SESSIONS[token]
        return None
    return session


def verify_admin_credentials(username: str, password: str) -> Optional[str]:
    """
    Verifies admin credentials using timing-safe comparison.
    If valid, creates and returns an admin session token.
    """
    user_ok = secrets.compare_digest(username.strip().lower(), ADMIN_USERNAME.lower())
    pass_ok = secrets.compare_digest(password.strip(), ADMIN_PASSWORD)

    if user_ok and pass_ok:
        admin_user = db.get_user("admin_master") or {
            "id": "admin_master",
            "name": "System Administrator",
            "email": "admin@novabrain.local",
            "role": "admin",
            "status": "active"
        }
        admin_key = db.get_active_key_for_user("admin_master")
        return create_user_session(admin_user, admin_key)
    return None


def verify_admin(
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> bool:
    """
    Dependency that enforces Admin-level authorization.
    Accepts:
    - X-Admin-Token header (Session Token with role='admin')
    - Master API Key in X-API-Key or Authorization header
    """
    # 1. Check Bearer token if provided
    bearer_token = None
    if authorization and authorization.startswith("Bearer "):
        bearer_token = authorization.replace("Bearer ", "").strip()

    candidate_token = x_admin_token or bearer_token

    # 2. Check Admin Session Token
    if candidate_token:
        sess = get_session_data(candidate_token)
        if sess and sess.get("role") == "admin":
            return True

    # 3. Check Master API Key
    master_key = get_or_generate_api_key()
    candidate_key = x_api_key or bearer_token
    if candidate_key and secrets.compare_digest(candidate_key.strip(), master_key):
        return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Admin authorization required. Please login with admin credentials."
    )


def verify_user_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """
    Authenticates incoming memory requests.
    Supports:
    1. X-API-Key header (Personal API key or Master API key)
    2. X-Session-Token header (Web Session Token)
    3. Authorization: Bearer <key_or_token>
    Resolves the exact tenant 'user' dictionary automatically.
    """
    bearer_token = None
    if authorization and authorization.startswith("Bearer "):
        bearer_token = authorization.replace("Bearer ", "").strip()

    # 1. Check Session Token
    session_candidate = x_session_token or bearer_token
    if session_candidate:
        sess = get_session_data(session_candidate)
        if sess:
            # Refresh user record from database
            fresh_user = db.get_user(sess["user_id"])
            if fresh_user and fresh_user.get("status") == "active":
                return fresh_user
            return sess["user"]

    # 2. Check API Key
    key_candidate = x_api_key or bearer_token
    if not key_candidate:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide 'X-API-Key' or 'X-Session-Token'."
        )

    # 3. Check Master API Key
    master_key = get_or_generate_api_key()
    if secrets.compare_digest(key_candidate.strip(), master_key):
        return {
            "id": "admin_master",
            "name": "System Administrator",
            "email": "admin@novabrain.local",
            "role": "admin",
            "status": "active"
        }

    # 4. Lookup individual user key in database
    user = db.verify_key_and_get_user(key_candidate.strip())
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, revoked, or suspended API key."
        )

    return user
