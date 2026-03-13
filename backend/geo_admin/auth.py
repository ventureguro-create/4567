"""
Geo Admin Module - Authentication
Simple token-based auth for admin access
"""
import os
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer

ADMIN_ACCESS_KEY = os.environ.get("ADMIN_ACCESS_KEY", "geo_admin_secret_2026")
SESSION_TTL_HOURS = 24

# In-memory session store (for simple MVP)
_admin_sessions = {}

security = HTTPBearer(auto_error=False)


def hash_key(key: str) -> str:
    """Hash the access key"""
    return hashlib.sha256(key.encode()).hexdigest()


def create_admin_session(access_key: str) -> Optional[str]:
    """Create admin session if key is valid"""
    if access_key != ADMIN_ACCESS_KEY:
        return None
    
    token = secrets.token_urlsafe(32)
    _admin_sessions[token] = {
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
    }
    return token


def validate_session(token: str) -> bool:
    """Validate admin session token"""
    if not token:
        return False
    
    session = _admin_sessions.get(token)
    if not session:
        return False
    
    if datetime.now(timezone.utc) > session["expires_at"]:
        del _admin_sessions[token]
        return False
    
    return True


def revoke_session(token: str) -> bool:
    """Revoke admin session"""
    if token in _admin_sessions:
        del _admin_sessions[token]
        return True
    return False


async def require_admin(request: Request):
    """Dependency to require admin authentication"""
    auth_header = request.headers.get("Authorization", "")
    
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if validate_session(token):
            return True
    
    # Also check query param for simple access
    key = request.query_params.get("admin_key")
    if key == ADMIN_ACCESS_KEY:
        return True
    
    raise HTTPException(status_code=401, detail="Admin authentication required")
