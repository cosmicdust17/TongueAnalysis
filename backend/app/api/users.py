from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import current_user, hash_password, verify_password
from app.models import User, AuditLog
from app.schemas import ProfileIn, PasswordIn
from app.services.common import user_dict, audit, iso

router = APIRouter(prefix='/users', tags=['个人信息'])

@router.get('/me')
def me(user: User = Depends(current_user)):
    return user_dict(user)

@router.put('/me')
def update_me(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.nickname = body.nickname
    user.profile = {'gender': body.gender, 'age': body.age}
    audit(db, user, '更新个人信息')
    db.commit()
    return user_dict(user)

@router.post('/me/password')
def password(body: PasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.password_hash:
        raise HTTPException(400, '微信或开发账号不支持修改密码，请使用对应登录方式')
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, '原密码错误')
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    audit(db, user, '修改密码并失效已有会话')
    db.commit()
    return {'ok': True, 'require_login': True}

@router.get('/me/logs')
def own_logs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).where(AuditLog.actor_id == user.id).order_by(AuditLog.created_at.desc()).limit(100)).all()
    return {'items': [dict(id=x.id, action=x.action, category=x.category, status=x.status, created_at=iso(x.created_at), actor_name=x.actor_name) for x in rows]}
