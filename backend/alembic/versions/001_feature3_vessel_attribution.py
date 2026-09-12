"""Add Feature 3 evidence scoring fields to vessels table

Revision ID: 001_feature3
Revises: 
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001_feature3'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Safe column additions
    with op.batch_alter_table('vessels') as batch_op:
        batch_op.add_column(sa.Column('composite_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('risk_class', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('scoring_mode', sa.String(), nullable=True, server_default='UNCERTAINTY_AWARE_5_FACTOR'))
        batch_op.add_column(sa.Column('origin_presence_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('behavior_anomaly_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('dwell_time_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('ais_gap_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('approach_departure_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('evidence_metrics', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('quality_flags', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('trajectory_geojson', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('explanation', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))

def downgrade():
    with op.batch_alter_table('vessels') as batch_op:
        batch_op.drop_column('created_at')
        batch_op.drop_column('explanation')
        batch_op.drop_column('trajectory_geojson')
        batch_op.drop_column('quality_flags')
        batch_op.drop_column('evidence_metrics')
        batch_op.drop_column('approach_departure_score')
        batch_op.drop_column('ais_gap_score')
        batch_op.drop_column('dwell_time_score')
        batch_op.drop_column('behavior_anomaly_score')
        batch_op.drop_column('origin_presence_score')
        batch_op.drop_column('scoring_mode')
        batch_op.drop_column('risk_class')
        batch_op.drop_column('composite_score')
