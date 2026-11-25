from datetime import date, timedelta
from hashlib import sha256
from unicodedata import normalize

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from app.api.analyses import owned_analysis
from app.core.database import get_db
from app.core.security import require_role
from app.models import Analysis, Report, SymptomCheckin, SymptomSuggestionDismissal, SymptomTracking, User, now
from app.schemas import SymptomCheckinIn, SymptomIn
from app.services.common import local_date, utc_day_start

router = APIRouter(prefix='/health-trends', tags=['健康趋势'])
user_only = require_role('user')
MAX_ACTIVE = 2
LEVEL_NAMES = ('没有', '轻微', '明显', '很明显')


def symptom_key(name):
    return sha256(name.casefold().encode()).hexdigest()


def lock_user(db, user_id):
    # Discard the auth read snapshot before taking the per-user write lock.
    db.rollback()
    # SQLite ignores FOR UPDATE, so take its write lock before reading tracking rows.
    if db.get_bind().dialect.name == 'sqlite':
        db.execute(update(User).where(User.id == user_id).values(active=User.active))
    else:
        db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    return user_id


def owned_tracking(db, user_id, tracking_id):
    item = db.scalar(select(SymptomTracking).where(SymptomTracking.id == tracking_id, SymptomTracking.user_id == user_id))
    if item is None:
        raise HTTPException(404, '症状追踪项不存在')
    return item


def new_symptoms(db, item):
    if item.status != 'completed' or not item.confirmed_symptoms:
        return {}
    previous = db.scalar(select(Analysis.confirmed_symptoms).where(
        Analysis.user_id == item.user_id, Analysis.status == 'completed',
        (Analysis.created_at < item.created_at) | (
            (Analysis.created_at == item.created_at) & (Analysis.id < item.id)
        ),
    ).order_by(Analysis.created_at.desc(), Analysis.id.desc()).limit(1))
    prior_keys = {symptom_key(name) for name in (previous or [])}
    candidates = {}
    for name in item.confirmed_symptoms:
        key = symptom_key(name)
        if key not in prior_keys:
            candidates.setdefault(key, name)
    return candidates


def tracking_view(item):
    return {'id': item.id, 'symptom_name': item.symptom_name, 'active': item.active}


def checkin_view(item):
    return {'date': item.record_date, 'level': item.level, 'level_name': LEVEL_NAMES[item.level]}


@router.get('/trackings')
def trackings(user: User = Depends(user_only), db: Session = Depends(get_db)):
    today = local_date(now())
    rows = db.execute(select(SymptomTracking, SymptomCheckin.level).outerjoin(
        SymptomCheckin, and_(SymptomCheckin.tracking_id == SymptomTracking.id, SymptomCheckin.record_date == today),
    ).where(SymptomTracking.user_id == user.id).order_by(SymptomTracking.active.desc(), SymptomTracking.id)).all()
    return {'date': today, 'max_active': MAX_ACTIVE, 'active_count': sum(item.active for item, _ in rows),
            'items': [{**tracking_view(item), 'today_level': level} for item, level in rows]}


@router.post('/trackings')
def start(body: SymptomIn, user: User = Depends(user_only), db: Session = Depends(get_db)):
    user_id = lock_user(db, user.id)
    key = symptom_key(body.symptom_name)
    owned = select(SymptomTracking).where(SymptomTracking.user_id == user_id)
    item = db.scalar(owned.where(SymptomTracking.symptom_key == key))
    if item is not None and item.active:
        return tracking_view(item)
    active_count = db.scalar(select(func.count()).select_from(SymptomTracking).where(
        SymptomTracking.user_id == user_id, SymptomTracking.active.is_(True),
    ))
    if active_count >= MAX_ACTIVE:
        raise HTTPException(409, {'code': 'tracking_limit_reached', 'message': '最多同时追踪两项症状', 'max_active': MAX_ACTIVE})
    if item is None:
        item = SymptomTracking(user_id=user_id, symptom_key=key, symptom_name=body.symptom_name,
                               started_date=local_date(now()))
        db.add(item)
    else:
        item.active = True
    db.commit()
    return tracking_view(item)


@router.put('/trackings/{tracking_id}/stop')
def stop(tracking_id: str, user: User = Depends(user_only), db: Session = Depends(get_db)):
    user_id = lock_user(db, user.id)
    item = owned_tracking(db, user_id, tracking_id)
    item.active = False
    db.commit()
    return tracking_view(item)


@router.get('/analyses/{analysis_id}/suggestion')
def suggestion(analysis_id: str, user: User = Depends(user_only), db: Session = Depends(get_db)):
    item = owned_analysis(db, user.id, analysis_id)
    candidates = new_symptoms(db, item)
    if not candidates:
        return {'suggestion': None}
    active = set(db.scalars(select(SymptomTracking.symptom_key).where(
        SymptomTracking.user_id == user.id, SymptomTracking.active.is_(True),
    )))
    if len(active) >= MAX_ACTIVE:
        return {'suggestion': None}
    dismissed = set(db.scalars(select(SymptomSuggestionDismissal.symptom_key).where(
        SymptomSuggestionDismissal.user_id == user.id, SymptomSuggestionDismissal.symptom_key.in_(candidates),
    )))
    name = next((name for key, name in candidates.items() if key not in active and key not in dismissed), None)
    return {'suggestion': {'symptom_name': name} if name is not None else None}


@router.put('/analyses/{analysis_id}/dismissal')
def dismiss(analysis_id: str, body: SymptomIn, user: User = Depends(user_only), db: Session = Depends(get_db)):
    user_id = lock_user(db, user.id)
    item = owned_analysis(db, user_id, analysis_id)
    key = symptom_key(body.symptom_name)
    candidates = new_symptoms(db, item)
    if key not in candidates:
        raise HTTPException(409, {'code': 'suggestion_unavailable', 'message': '该症状不属于本次分析的可处理建议'})
    if db.get(SymptomSuggestionDismissal, (user_id, key)) is None:
        db.add(SymptomSuggestionDismissal(user_id=user_id, symptom_key=key))
    db.commit()
    return {'symptom_name': candidates[key], 'dismissed': True}


@router.put('/trackings/{tracking_id}/checkins/today')
def checkin(tracking_id: str, body: SymptomCheckinIn, user: User = Depends(user_only), db: Session = Depends(get_db)):
    user_id = lock_user(db, user.id)
    tracking = owned_tracking(db, user_id, tracking_id)
    if not tracking.active:
        raise HTTPException(409, {'code': 'tracking_paused', 'message': '请先恢复追踪再填写自评'})
    today = local_date(now())
    item = db.get(SymptomCheckin, (tracking.id, today))
    if item is None:
        item = SymptomCheckin(tracking_id=tracking.id, record_date=today, level=body.level)
        db.add(item)
    else:
        item.level = body.level
    db.commit()
    return checkin_view(item)


def report_history(db, tracking, start_date, end_date):
    if tracking.started_date is None or start_date >= tracking.started_date:
        return []
    stop = min(end_date + timedelta(days=1), tracking.started_date)
    rows = db.execute(select(Report.id, Report.created_at, Analysis.symptoms)
                      .join(Analysis, Analysis.id == Report.analysis_id)
                      .where(Report.user_id == tracking.user_id, Analysis.user_id == tracking.user_id,
                             Analysis.status == 'completed', Report.created_at >= utc_day_start(start_date),
                             Report.created_at < utc_day_start(stop))
                      .order_by(Report.created_at.desc(), Report.id.desc()))
    day_entries = {}
    symptom = tracking.symptom_name.casefold()
    for report_id, created_at, symptoms in rows:
        day = local_date(created_at)
        entry = day_entries.setdefault(day, {'date': day, 'mention_count': 0, 'report_id': None})
        text = ' '.join(normalize('NFKC', symptoms).split()).casefold()
        if symptom in text:
            entry['mention_count'] += 1
            if entry['report_id'] is None:
                entry['report_id'] = report_id
    return [day_entries[day] for day in sorted(day_entries)]


@router.get('/trackings/{tracking_id}/trend')
def trend(tracking_id: str,
          start_date: date = Query(ge=date(1000, 1, 2), le=date(9999, 12, 30)),
          end_date: date = Query(ge=date(1000, 1, 2), le=date(9999, 12, 30)),
          user: User = Depends(user_only), db: Session = Depends(get_db)):
    tracking = owned_tracking(db, user.id, tracking_id)
    if start_date > end_date:
        raise HTTPException(422, '开始日期不能晚于结束日期')
    checkin_start = max(start_date, tracking.started_date) if tracking.started_date else start_date
    rows = db.scalars(select(SymptomCheckin).where(
        SymptomCheckin.tracking_id == tracking.id, SymptomCheckin.record_date.between(checkin_start, end_date),
    ).order_by(SymptomCheckin.record_date))
    return {'tracking_id': tracking.id, 'symptom_name': tracking.symptom_name, 'started_date': tracking.started_date,
            'report_history': report_history(db, tracking, start_date, end_date),
            'items': [checkin_view(item) for item in rows]}
