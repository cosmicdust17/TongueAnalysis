from threading import Lock
from time import monotonic
from uuid import uuid4
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.core.database import get_db
from app.core.security import current_user, verify_password, issue_token
from app.models import User
from app.schemas import LoginIn, WechatIn, DevLoginIn
from app.services.common import user_dict, audit

router = APIRouter(prefix='/auth', tags=['认证'])
_attempts, _lock = {}, Lock()

def rate_limit(request):
    key = request.client.host if request.client else 'unknown'
    t = monotonic()
    with _lock:
        for old in list(_attempts):
            if not _attempts[old] or t - _attempts[old][-1] > 60:
                _attempts.pop(old)
        history = [x for x in _attempts.get(key, []) if t - x < 60]
        if len(history) >= 20:
            raise HTTPException(429, '登录请求过于频繁，请稍后重试')
        _attempts[key] = history + [t]

def session_result(user):
    return {'access_token': issue_token(user), 'token_type': 'bearer', 'user': user_dict(user)}

@router.post('/login')
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(request)
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, '账号或密码错误，或账号已停用')
    audit(db, user, '账号登录')
    db.commit()
    return session_result(user)

@router.post('/dev-login')
def dev_login(body: DevLoginIn, request: Request, db: Session = Depends(get_db)):
    if settings().app_env != 'development' or not settings().dev_login_enabled:
        raise HTTPException(404, '接口不存在')
    rate_limit(request)
    username = 'dev_' + body.role
    user = db.scalar(select(User).where(User.username == username))
    if not user:
        user = User(username=username, role=body.role, nickname={'user': '健康体验者', 'knowledge_admin': '知识管理员', 'ops_admin': '运维管理员'}[body.role])
        db.add(user)
        db.flush()
    if not user.active:
        raise HTTPException(403, '账号已停用')
    audit(db, user, '开发联调登录')
    db.commit()
    return session_result(user)

@router.post('/wechat')
async def wechat_login(body: WechatIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(request)
    s = settings()
    if not s.wechat_appid or not s.wechat_secret:
        raise HTTPException(503, '尚未配置微信登录，请使用管理员账号或开发联调入口')
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get('https://api.weixin.qq.com/sns/jscode2session', params={'appid': s.wechat_appid, 'secret': s.wechat_secret, 'js_code': body.code, 'grant_type': 'authorization_code'})
            response.raise_for_status()
            data = response.json()
        openid = data.get('openid')
        error = data.get('errcode', 0)
        if error in (40029, 40163):
            raise HTTPException(401, '微信登录凭证已失效，请重新点击微信登录')
        if error in (40013, 40125, 40001, 40164):
            raise HTTPException(503, '微信登录配置异常，请联系管理员检查小程序配置及服务器IP白名单')
        if error == 45011:
            raise HTTPException(429, '微信登录过于频繁，请稍后重试')
        if error == 40226:
            raise HTTPException(403, '微信暂时限制了此次登录，请稍后重试')
        if error or not isinstance(openid, str) or not openid or len(openid) > 128:
            raise HTTPException(503, '微信登录服务暂时不可用，请稍后重试')
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        raise HTTPException(503, '微信登录服务暂时不可用，请稍后重试') from None
    user = db.scalar(select(User).where(User.openid == openid))
    if not user:
        user = User(username='wx_' + uuid4().hex[:24], openid=openid, role='user')
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            user = db.scalar(select(User).where(User.openid == openid))
            if not user:
                raise HTTPException(503, '微信登录暂时失败，请重新点击微信登录') from None
    if not user.active or user.role != 'user':
        raise HTTPException(403, '账号已停用')
    audit(db, user, '微信登录')
    db.commit()
    return session_result(user)

@router.post('/logout')
def logout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.token_version += 1
    audit(db, user, '退出登录')
    db.commit()
    return {'ok': True}
