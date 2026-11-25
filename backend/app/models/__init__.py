from datetime import date, datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, Integer, Boolean, Date, DateTime, JSON, ForeignKey, Index, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

def uid():
    return str(uuid4())

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    openid: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(256), default='')
    nickname: Mapped[str] = mapped_column(String(80), default='健康体验者')
    role: Mapped[str] = mapped_column(String(32), default='user')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class StoredFile(Base):
    __tablename__ = 'stored_files'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(120))
    purpose: Mapped[str] = mapped_column(String(24))
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Analysis(Base):
    __tablename__ = 'analyses'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    image_id: Mapped[str] = mapped_column(ForeignKey('stored_files.id'))
    symptoms: Mapped[str] = mapped_column(Text)
    confirmed_symptoms: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    duration: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), default='queued', index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default='')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime().with_variant(MySQLDateTime(fsp=6), 'mysql'), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

class Report(Base):
    __tablename__ = 'reports'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey('analyses.id'), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(160), default='舌象综合分析报告')
    content: Mapped[dict] = mapped_column(JSON)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Evidence(Base):
    __tablename__ = 'report_evidence'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    report_id: Mapped[str] = mapped_column(ForeignKey('reports.id'), index=True)
    graph_entity_id: Mapped[str] = mapped_column(String(36))
    snapshot: Mapped[dict] = mapped_column(JSON)

class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    file_id: Mapped[str | None] = mapped_column(ForeignKey('stored_files.id'), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    citation: Mapped[str] = mapped_column(Text, default='')
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_name: Mapped[str] = mapped_column(String(80), default='system')
    category: Mapped[str] = mapped_column(String(24), default='operation')
    action: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24), default='success')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)

class Alert(Base):
    __tablename__ = 'alerts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    service: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(String(240))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class SymptomTracking(Base):
    __tablename__ = 'symptom_trackings'
    __table_args__ = (UniqueConstraint('user_id', 'symptom_key', name='uq_tracking_user_symptom'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    symptom_key: Mapped[str] = mapped_column(String(64))
    symptom_name: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    started_date: Mapped[date | None] = mapped_column(Date, nullable=True)

class SymptomSuggestionDismissal(Base):
    __tablename__ = 'symptom_suggestion_dismissals'

    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    symptom_key: Mapped[str] = mapped_column(String(64), primary_key=True)

class SymptomCheckin(Base):
    __tablename__ = 'symptom_checkins'
    __table_args__ = (CheckConstraint('level BETWEEN 0 AND 3', name='ck_symptom_checkin_level'),)

    tracking_id: Mapped[str] = mapped_column(ForeignKey('symptom_trackings.id'), primary_key=True)
    record_date: Mapped[date] = mapped_column(Date, primary_key=True)
    level: Mapped[int] = mapped_column(Integer)

Index('ix_reports_user_created', Report.user_id, Report.created_at)
Index('ix_analyses_user_status_created', Analysis.user_id, Analysis.status, Analysis.created_at)
