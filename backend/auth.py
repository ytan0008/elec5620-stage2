from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session
from backend.config import settings
from backend.db import get_db
from backend.models import User

hasher = PasswordHash.recommended()
bearer = HTTPBearer()


def hash_password(password: str) -> str:
    return hasher.hash(password)


def token_for(user: User) -> str:
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": datetime.now(timezone.utc) + timedelta(hours=24)}, settings().jwt_secret, algorithm="HS256")


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(credentials.credentials, settings().jwt_secret, algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
        if user is None or user.role != payload["role"]:
            raise ValueError("Account not found")
        return user
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Invalid or expired token")


def learner(user: User = Depends(current_user)) -> User:
    if user.role != "learner":
        raise HTTPException(403, "Learner role required")
    return user


def instructor(user: User = Depends(current_user)) -> User:
    if user.role != "instructor":
        raise HTTPException(403, "Instructor role required")
    return user
