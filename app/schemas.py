from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


# ============================================================
# Core Memory Models
# ============================================================

class RecallRequest(BaseModel):
    query: str = Field(..., description="The search query or prompt to retrieve relevant memories for")
    agent_id: Optional[str] = Field(None, description="Optional agent or client device identifier (e.g. 'pc_assistant', 'mobile_app')")
    top_k: Optional[int] = Field(3, ge=1, le=20, description="Maximum number of memories to return")


class RecallResponse(BaseModel):
    success: bool = True
    user_id: str
    query: str
    memories: List[str]
    count: int
    raw: Optional[List[Dict[str, Any]]] = None


class LearnRequest(BaseModel):
    message: Union[str, List[Dict[str, str]]] = Field(
        ...,
        description="Text message or conversation turns ([{'role': 'user', 'content': '...'}])"
    )
    agent_id: Optional[str] = Field(None, description="Optional agent / device identifier")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata key-value pairs")


class LearnResponse(BaseModel):
    success: bool = True
    user_id: str
    status: str
    message: str


# ============================================================
# Profile, Stats & Portability Models
# ============================================================

class ProfileResponse(BaseModel):
    success: bool = True
    user_id: str
    total_facts: int
    summary: str
    facts: List[str]


class StatsResponse(BaseModel):
    status: str
    total_memories: int
    collection: str
    db_provider: str
    uptime_seconds: float
    timestamp: str


class ResetResponse(BaseModel):
    success: bool = True
    user_id: str
    message: str


class DeleteResponse(BaseModel):
    success: bool = True
    message: str


class ExportResponse(BaseModel):
    success: bool = True
    user_id: str
    exported_at: str
    count: int
    memories: List[Dict[str, Any]]


class ImportRequest(BaseModel):
    memories: List[str] = Field(..., description="List of raw memory statements or facts to import")


class ImportResponse(BaseModel):
    success: bool = True
    user_id: str
    imported_count: int
    message: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str


# ============================================================
# Authentication & Multi-User Governance Models
# ============================================================

class UserSignUpRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=60, description="Full name of the user")
    email: str = Field(..., min_length=4, max_length=120, description="Email address for login")
    password: str = Field(..., min_length=4, description="Secret password")


class UserLoginRequest(BaseModel):
    email: str = Field(..., description="Email or Admin username (e.g. 'admin')")
    password: str = Field(..., description="Password")


class AuthResponse(BaseModel):
    success: bool = True
    token: str
    user: Dict[str, Any]
    api_key: str
    message: str = "Authentication successful"


class ApiKeyResponse(BaseModel):
    success: bool = True
    api_key: str
    key_prefix: str
    name: str


class AdminLoginRequest(BaseModel):
    username: str = Field(..., description="Admin username (default: admin)")
    password: str = Field(..., description="Admin password (default: admin123)")


class AdminLoginResponse(BaseModel):
    success: bool = True
    token: str
    expires_in_hours: int = 24
    message: str


class UserCreateRequest(BaseModel):
    name: str = Field(..., description="Full name of the user (e.g. 'Amit')")
    email: str = Field(..., description="Unique email address")
    role: Optional[str] = Field("user", description="User role ('user' or 'admin')")
    password: Optional[str] = Field(None, description="Optional custom password")


class UserCreateResponse(BaseModel):
    success: bool = True
    user: Dict[str, Any]
    api_key: str
    note: str = "Save this API key. You can also view it in your dashboard."


class KeyCreateRequest(BaseModel):
    name: Optional[str] = Field("Client Device", description="Descriptive label for this key (e.g. 'Flutter App')")


class KeyCreateResponse(BaseModel):
    success: bool = True
    key_id: str
    api_key: str
    key_prefix: str
    name: str


class UserStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="'active' or 'suspended'")


class AdminUserDetailResponse(BaseModel):
    success: bool = True
    user: Dict[str, Any]
    keys: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    memories: List[Dict[str, Any]]
    memories_count: int


class AdminDashboardResponse(BaseModel):
    metrics: Dict[str, Any]
    users: List[Dict[str, Any]]
    recent_logs: List[Dict[str, Any]]
