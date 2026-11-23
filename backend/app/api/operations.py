from datetime import datetime, timedelta, timezone, time
from pathlib import Path
from tempfile import TemporaryFile
from zoneinfo import ZoneInfo
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.core.security import require_role
from app.models import User, AuditLog, Alert, Analysis, Report
from app.schemas import UserStatusIn
from app.services.common import user_dict, audit, iso
from app.repositories.graph_repository import graph_repository

router = APIRouter(prefix='/operations', tags=['运维管理'])
admin = require_role('ops_admin')

def services(db):
    s = settings()
    result = []
    def probe(key, title, action):
        try:
            action()
            result.append({'key': key, 'name': title, 'status': 'online', 'message': '检查通过'})
        except Exception:
            result.append({'key': key, 'name': title, 'status': 'offline', 'message': '检查失败，请检查配置及服务日志'})
    probe('mysql', '业务数据库', lambda: db.execute(text('SELECT 1')))
    if s.knowledge_retrieval_enabled:
        probe('graph', '知识图谱' + ('（本地联调）' if s.graph_provider == 'demo' else '（Neo4j）'), graph_repository().ping)
    else:
        result.append({'key': 'graph', 'name': '知识检索', 'status': 'disabled', 'message': '知识检索尚未启用'})
    def storage():
        path = Path(s.storage_path)
        path.mkdir(parents=True, exist_ok=True)
        with TemporaryFile(dir=path) as file:
            file.write(b'probe')
    probe('storage', '文件存储', storage)
    if s.model_provider == 'mock':
        result.append({'key': 'model', 'name': '图像与文本分析', 'status': 'mock', 'message': '固定模拟结果，模型尚未接入'})
    else:
        def model():
            headers = {'Authorization': f'Bearer {s.model_api_key}'} if s.model_api_key else {}
            with httpx.Client(timeout=3, trust_env=False) as client:
                response = client.get(s.model_base_url.rstrip('/') + '/health', headers=headers)
                response.raise_for_status()
                if response.json().get('ready') is not True:
                    raise ValueError('Model not ready')
        probe('model', '图像与文本分析', model)
    result.append({'key': 'report', 'name': '报告生成模块', 'status': 'online', 'message': '证据约束模板已加载'})
    return result

@router.get('/overview')
def overview(user: User = Depends(admin), db: Session = Depends(get_db)):
    shanghai = ZoneInfo('Asia/Shanghai')
    today = datetime.combine(datetime.now(shanghai).date(), time.min, tzinfo=shanghai).astimezone(timezone.utc).replace(tzinfo=None)
    checks = services(db)
    logs = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(5)).all()
    return {'updated_at': datetime.now(timezone.utc).isoformat(), 'services': checks,
            'status': 'degraded' if any(s['status'] == 'offline' for s in checks) else 'mock' if settings().model_provider == 'mock' else 'online',
            'today_analyses': db.scalar(select(func.count()).select_from(Analysis).where(Analysis.created_at >= today)),
            'report_count': db.scalar(select(func.count()).select_from(Report)),
            'pending_alerts': db.scalar(select(func.count()).select_from(Alert).where(Alert.resolved.is_(False))),
            'recent_logs': [dict(id=x.id, action=x.action, status=x.status, created_at=iso(x.created_at)) for x in logs]}

@router.get('/logs')
def logs(q: str = Query(default='', max_length=100), category: str = '', date: str = '', page: int = Query(default=1, ge=1), page_size: int = Query(default=30, ge=1, le=100), user: User = Depends(admin), db: Session = Depends(get_db)):
    stmt = select(AuditLog)
    if q:
        stmt = stmt.where(AuditLog.action.contains(q, autoescape=True))
    if category:
        stmt = stmt.where(AuditLog.category == category)
    if date:
        try:
            start = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            raise HTTPException(422, '日期格式需要为 YYYY-MM-DD')
        stmt = stmt.where(AuditLog.created_at >= start, AuditLog.created_at < start + timedelta(days=1))
    count = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditLog.created_at.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {'items': [dict(id=x.id, action=x.action, category=x.category, status=x.status, actor_name=x.actor_name, created_at=iso(x.created_at)) for x in rows], 'total': count}

@router.get('/alerts')
def alerts(user: User = Depends(admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(Alert).order_by(Alert.created_at.desc()).limit(100)).all()
    return {'items': [dict(id=x.id, service=x.service, message=x.message, resolved=x.resolved, created_at=iso(x.created_at)) for x in rows]}

@router.post('/alerts/{aid}/resolve')
def resolve(aid: str, user: User = Depends(admin), db: Session = Depends(get_db)):
    row = db.get(Alert, aid)
    if not row:
        raise HTTPException(404, '告警不存在')
    row.resolved = True
    audit(db, user, '标记告警已处理')
    db.commit()
    return {'ok': True}

@router.get('/users')
def users(q: str = Query(default='', max_length=80), page: int = Query(default=1, ge=1), user: User = Depends(admin), db: Session = Depends(get_db)):
    stmt = select(User).where(User.role == 'user')
    if q:
        stmt = stmt.where(User.username.contains(q, autoescape=True) | User.nickname.contains(q, autoescape=True))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(User.created_at.desc()).offset((page-1)*30).limit(30)).all()
    return {'items': [user_dict(x) for x in rows], 'total': total}

@router.put('/users/{uid}/status')
def status(uid: str, body: UserStatusIn, user: User = Depends(admin), db: Session = Depends(get_db)):
    target = db.get(User, uid)
    if not target or target.role != 'user':
        raise HTTPException(404, '用户不存在')
    target.active = body.active
    target.token_version += 1
    audit(db, user, '启用用户账号' if body.active else '停用用户账号')
    db.commit()
    return user_dict(target)

@router.get('/configuration')
def configuration(user: User = Depends(admin)):
    s = settings()
    return {'app_env': s.app_env, 'model_provider': s.model_provider, 'model_timeout_seconds': s.model_timeout_seconds,
            'graph_provider': s.graph_provider, 'knowledge_retrieval_enabled': s.knowledge_retrieval_enabled, 'worker_enabled': s.worker_enabled,
            'upload_max_mb': s.upload_max_mb, 'wechat_appid': s.wechat_appid,
            'wechat_configured': bool(s.wechat_appid and s.wechat_secret)}
