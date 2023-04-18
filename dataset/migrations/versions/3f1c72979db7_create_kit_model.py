"""create kit model

Revision ID: 3f1c72979db7
Revises: 
Create Date: 2023-04-18 08:01:05.710359

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3f1c72979db7'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('kit',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('import_id', sa.String(length=128), nullable=False),
    sa.Column('citizen_id', sa.Integer(), nullable=False),
    sa.Column('town', sa.String(length=256), nullable=False),
    sa.Column('street', sa.String(length=256), nullable=False),
    sa.Column('building', sa.String(length=256), nullable=False),
    sa.Column('apartment', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=256), nullable=False),
    sa.Column('birth_date', sa.Date(), nullable=False),
    sa.Column('gender', sa.String(length=6), nullable=False),
    sa.Column('relatives', sa.ARRAY(sa.Integer()), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('import_id', 'citizen_id', name='unique_import_citizen')
    )
    op.create_index(op.f('ix_kit_id'), 'kit', ['id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_kit_id'), table_name='kit')
    op.drop_table('kit')
    # ### end Alembic commands ###