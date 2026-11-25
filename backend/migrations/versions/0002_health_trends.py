"""Add explicit symptom confirmations, tracking, dismissals and daily check-ins."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('analyses', sa.Column('confirmed_symptoms', sa.JSON(), nullable=True))
    if op.get_context().dialect.name == 'mysql':
        # Rapid consecutive analyses must still have an unambiguous submission order.
        op.alter_column('analyses', 'created_at', existing_type=sa.DateTime(), type_=mysql.DATETIME(fsp=6), existing_nullable=False)
    op.create_index('ix_analyses_user_status_created', 'analyses', ['user_id', 'status', 'created_at'])
    op.create_table(
        'symptom_trackings',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('symptom_key', sa.String(64), nullable=False),
        sa.Column('symptom_name', sa.String(80), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('user_id', 'symptom_key', name='uq_tracking_user_symptom'),
    )
    op.create_table(
        'symptom_suggestion_dismissals',
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('symptom_key', sa.String(64), primary_key=True),
    )
    op.create_table(
        'symptom_checkins',
        sa.Column('tracking_id', sa.String(36), sa.ForeignKey('symptom_trackings.id'), primary_key=True),
        sa.Column('record_date', sa.Date(), primary_key=True),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.CheckConstraint('level BETWEEN 0 AND 3', name='ck_symptom_checkin_level'),
    )

def downgrade():
    op.drop_table('symptom_checkins')
    op.drop_table('symptom_suggestion_dismissals')
    op.drop_table('symptom_trackings')
    op.drop_index('ix_analyses_user_status_created', table_name='analyses')
    if op.get_context().dialect.name == 'mysql':
        op.alter_column('analyses', 'created_at', existing_type=mysql.DATETIME(fsp=6), type_=sa.DateTime(), existing_nullable=False)
    op.drop_column('analyses', 'confirmed_symptoms')
