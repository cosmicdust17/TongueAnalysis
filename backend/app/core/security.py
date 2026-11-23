import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)

def hash_password(value: str):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), 600000)
    return f'pbkdf2_sha256$600000${salt}${base64.b64encode(digest).decode()}'

def verify_password(value: str, encoded: str):
    try:
        _, iterations, salt, digest = encoded.split('$')
        actual = hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(base64.b64encode(actual).decode(), digest)
    except (ValueError, TypeError):
        return False

def issue_token(user: User):
    return jwt.encode({'sub': user.id, 'ver': user.token_version,
        'exp': datetime.now(timezone.utc) + timedelta(hours=settings().token_hours)},
        settings().jwt_secret, algorithm='HS256')

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    try:
        if not credentials:
            raise ValueError()
        payload = jwt.decode(credentials.credentials, settings().jwt_secret, algorithms=['HS256'])
        user = db.get(User, payload['sub'])
        if not user or not user.active or payload.get('ver') != user.token_version:
            raise ValueError()
        return user
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, '登录已过期，请重新登录')

def require_role(*roles):
    def check(user: User = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, '没有访问权限')
        return user
    return check
