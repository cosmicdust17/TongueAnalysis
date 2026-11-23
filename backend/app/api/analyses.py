from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import require_role
from app.models import Analysis, User, StoredFile, Report
from app.schemas import AnalysisIn
from app.services.common import iso, audit

router = APIRouter(prefix='/analyses', tags=['舌象分析'])
user_only = require_role('user')

def view(item, db):
    report_id = db.scalar(select(Report.id).where(Report.analysis_id == item.id))
    return {'id': item.id, 'status': item.status, 'progress': item.progress, 'error': item.error,
            'report_id': report_id, 'created_at': iso(item.created_at), 'updated_at': iso(item.updated_at)}

@router.post('', status_code=202)
def create(body: AnalysisIn, user: User = Depends(user_only), db: Session = Depends(get_db)):
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    file = db.get(StoredFile, body.image_id)
    if not file or file.owner_id != user.id or file.purpose != 'image':
        raise HTTPException(400, '请先上传本人的舌象图片')
    pending = db.scalar(select(Analysis.id).where(Analysis.user_id == user.id, Analysis.status.in_(['queued', 'running'])).with_for_update())
    if pending:
        raise HTTPException(409, {'message': '已有分析任务正在处理', 'analysis_id': pending})
    item = Analysis(user_id=user.id, **body.model_dump())
    db.add(item)
    audit(db, user, '提交舌象分析')
    db.commit()
    return view(item, db)

@router.get('/{aid}')
def get(aid: str, user: User = Depends(user_only), db: Session = Depends(get_db)):
    item = db.get(Analysis, aid)
    if not item or item.user_id != user.id:
        raise HTTPException(404, '分析任务不存在')
    return view(item, db)

@router.post('/{aid}/retry', status_code=202)
def retry(aid: str, user: User = Depends(user_only), db: Session = Depends(get_db)):
    item = db.get(Analysis, aid)
    if not item or item.user_id != user.id:
        raise HTTPException(404, '分析任务不存在')
    if item.status != 'failed':
        raise HTTPException(409, '只有失败的任务可以重试')
    if db.scalar(select(Analysis.id).where(Analysis.user_id == user.id, Analysis.status.in_(['queued', 'running'])).with_for_update()):
        raise HTTPException(409, '请等待当前分析任务完成')
    item.status, item.progress, item.error = 'queued', 0, ''
    audit(db, user, '重试分析任务')
    db.commit()
    return view(item, db)
