"""Record the first known tracking day in Beijing time."""

from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('symptom_trackings', sa.Column('started_date', sa.Date(), nullable=True))


def downgrade():
    op.drop_column('symptom_trackings', 'started_date')
