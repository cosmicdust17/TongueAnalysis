"""Initial business schema. Frozen column definitions, independent of future models."""
from alembic import op
import sqlalchemy as sa
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('users',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('username', sa.String(80), nullable=False, unique=True),
        sa.Column('openid', sa.String(128), unique=True), sa.Column('password_hash', sa.String(256), nullable=False),
        sa.Column('nickname', sa.String(80), nullable=False), sa.Column('role', sa.String(32), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False), sa.Column('token_version', sa.Integer(), nullable=False),
        sa.Column('profile', sa.JSON(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_table('stored_files',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('original_name', sa.String(255), nullable=False), sa.Column('path', sa.String(512), nullable=False),
        sa.Column('content_type', sa.String(120), nullable=False), sa.Column('purpose', sa.String(24), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_index('ix_stored_files_owner_id', 'stored_files', ['owner_id'])
    op.create_table('analyses',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('image_id', sa.String(36), sa.ForeignKey('stored_files.id'), nullable=False), sa.Column('symptoms', sa.Text(), nullable=False),
        sa.Column('duration', sa.String(40), nullable=False), sa.Column('status', sa.String(24), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False), sa.Column('error', sa.Text(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False), sa.Column('updated_at', sa.DateTime(), nullable=False))
    op.create_index('ix_analyses_user_id', 'analyses', ['user_id'])
    op.create_index('ix_analyses_status', 'analyses', ['status'])
    op.create_table('reports',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('analysis_id', sa.String(36), sa.ForeignKey('analyses.id'), nullable=False, unique=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False), sa.Column('title', sa.String(160), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False), sa.Column('is_demo', sa.Boolean(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_index('ix_reports_user_id', 'reports', ['user_id'])
    op.create_index('ix_reports_user_created', 'reports', ['user_id', 'created_at'])
    op.create_table('report_evidence',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('report_id', sa.String(36), sa.ForeignKey('reports.id'), nullable=False),
        sa.Column('graph_entity_id', sa.String(36), nullable=False), sa.Column('snapshot', sa.JSON(), nullable=False))
    op.create_index('ix_report_evidence_report_id', 'report_evidence', ['report_id'])
    op.create_table('documents',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('file_id', sa.String(36), sa.ForeignKey('stored_files.id')),
        sa.Column('title', sa.String(200), nullable=False), sa.Column('citation', sa.Text(), nullable=False),
        sa.Column('is_demo', sa.Boolean(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_table('audit_logs',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('actor_id', sa.String(36)),
        sa.Column('actor_name', sa.String(80), nullable=False), sa.Column('category', sa.String(24), nullable=False),
        sa.Column('action', sa.String(200), nullable=False), sa.Column('status', sa.String(24), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_index('ix_audit_logs_actor_id', 'audit_logs', ['actor_id'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_table('alerts',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('service', sa.String(80), nullable=False),
        sa.Column('message', sa.String(240), nullable=False), sa.Column('resolved', sa.Boolean(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False))

def downgrade():
    for name in ['alerts', 'audit_logs', 'documents', 'report_evidence', 'reports', 'analyses', 'stored_files', 'users']:
        op.drop_table(name)
