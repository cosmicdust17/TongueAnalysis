from datetime import datetime, timezone
from app.models import AuditLog

def iso(value):
    # DB timestamps are UTC; emit explicit offset for the mini-program.
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None

def user_dict(user):
    return {'id': user.id, 'username': user.username, 'nickname': user.nickname,
            'role': user.role, 'active': user.active, 'profile': user.profile,
            'has_password': bool(user.password_hash), 'created_at': iso(user.created_at)}

def audit(db, actor, action, category='operation', status='success'):
    db.add(AuditLog(actor_id=actor.id if actor else None,
        actor_name=actor.username if actor else 'system', action=action,
        category=category, status=status))
