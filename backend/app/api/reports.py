from fastapi import APIRouter, Depends, HTTPException, Query, Response
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import require_role
from app.models import User, Report, Evidence, Analysis, StoredFile
from app.services.annotations import annotation_snapshot
from app.services.common import iso, audit, local_date, utc_day_start
from app.services.export_service import render_report
from app.services.report_presentation import compose, merge_saved_presentation, PRESENTATION_VERSION

router = APIRouter(prefix='/reports', tags=['报告与历史记录'])
user_only = require_role('user')

def owned(rid, user, db):
    item = db.get(Report, rid)
    if not item or item.user_id != user.id:
        raise HTTPException(404, '报告不存在')
    return item

def detail(item, db):
    analysis = db.get(Analysis, item.analysis_id)
    ensure_presentation(item, analysis, db)
    return {'id': item.id, 'title': item.title, 'analysis_id': item.analysis_id,
            'image_id': analysis.image_id, 'is_demo': item.is_demo, 'content': item.content, 'created_at': iso(item.created_at)}


def ensure_presentation(item, analysis, db):
    if 'annotations' not in item.content:
        image = db.get(StoredFile, analysis.image_id)
        if image and Path(image.path).is_file():
            result = analysis.result or {}
            if not result.get('fusion_result') and 'yolo_detections' in item.content:
                result = {'fusion_result': {'detections': item.content['yolo_detections']}}
            item.content = {**item.content, 'annotations': annotation_snapshot(result, image.path, item.content['model_version'])}
            db.commit()
    previous = item.content.get('presentation', {})
    version = previous.get('version', 0)
    if 2 <= version < PRESENTATION_VERSION:
        item.content = {**item.content, 'presentation': merge_saved_presentation(previous)}
        db.commit()
    elif version < 2:
        if previous:
            profile = dict(previous['identity'])
        else:
            profile = db.get(User, item.user_id).profile or {}
        sources = [e.snapshot for e in db.scalars(select(Evidence).where(Evidence.report_id == item.id)).all()]
        raw = {**item.content}
        generated = (analysis.result or {}).get('fusion_result', {}).get('qwen', {})
        if generated.get('status') == 'valid':
            raw['summary'] = generated['output'].get('analysis', raw.get('summary',''))
        item.content = {**item.content, 'presentation': compose(raw, analysis.symptoms, analysis.duration, item.user_id, profile, item.created_at, sources)}
        db.commit()

def completed_photos_in_range(stmt, user_id, first, last):
    return stmt.join(StoredFile, StoredFile.id == Analysis.image_id).where(
        Analysis.user_id == user_id, Analysis.status == 'completed',
        StoredFile.owner_id == user_id, StoredFile.purpose == 'image',
        StoredFile.content_type.like('image/%'),
        StoredFile.created_at >= utc_day_start(first), StoredFile.created_at < utc_day_start(last),
    )

@router.get('')
def history(q: str = Query(default='', max_length=100), page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), day: date | None = Query(default=None, alias='date', ge=date(1000, 1, 2), le=date(9999, 12, 30)), user: User = Depends(user_only), db: Session = Depends(get_db)):
    stmt = select(Report).join(Analysis, Report.analysis_id == Analysis.id).where(Report.user_id == user.id)
    if day is not None:
        stmt = completed_photos_in_range(stmt, user.id, day, day + timedelta(days=1))
    if q:
        stmt = stmt.where(Report.title.contains(q, autoescape=True) | Analysis.symptoms.contains(q, autoescape=True))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(Report.created_at.desc(), Report.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {'items': [detail(x, db) for x in items], 'total': total, 'page': page, 'page_size': page_size}

@router.get('/calendar')
def calendar(month: str = Query(pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$'), user: User = Depends(user_only), db: Session = Depends(get_db)):
    if not '1000-02' <= month <= '9999-11':
        raise HTTPException(422, '月份超出可查询范围')
    first = date.fromisoformat(month + '-01')
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    stmt = select(StoredFile.created_at).select_from(Report).join(Analysis, Report.analysis_id == Analysis.id).where(Report.user_id == user.id)
    uploads = db.scalars(completed_photos_in_range(stmt, user.id, first, last))
    counts = Counter(local_date(timestamp).isoformat() for timestamp in uploads)
    return {'month': month, 'dates': sorted(counts), 'counts': dict(sorted(counts.items()))}

@router.get('/{rid}')
def get(rid: str, user: User = Depends(user_only), db: Session = Depends(get_db)):
    return detail(owned(rid, user, db), db)

@router.get('/{rid}/evidence')
def evidence(rid: str, user: User = Depends(user_only), db: Session = Depends(get_db)):
    owned(rid, user, db)
    return {'items': [e.snapshot for e in db.scalars(select(Evidence).where(Evidence.report_id == rid)).all()], 'snapshot': True}

@router.get('/{rid}/pdf')
def pdf(rid: str, user: User = Depends(user_only), db: Session = Depends(get_db)):
    item = owned(rid, user, db)
    analysis = db.get(Analysis, item.analysis_id)
    ensure_presentation(item, analysis, db)
    image = db.get(StoredFile, analysis.image_id)
    started = perf_counter()
    result = render_report(item, image.path if image else None)
    pdf_seconds = perf_counter()-started
    audit(db, user, '导出PDF报告')
    db.commit()
    return Response(result, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="tongue-report-{rid}.pdf"', 'Cache-Control': 'private, no-store', 'X-PDF-Render-Seconds': f'{pdf_seconds:.6f}'})
