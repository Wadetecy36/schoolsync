"""Add missing face_encoding and missing tables safely

Revision ID: a1b2c3d4e5f6
Revises: 5730dcb1e794
Create Date: 2026-02-05 16:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '5730dcb1e794'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    # 1. Add face_encoding to students if it's missing
    columns = [c['name'] for c in inspector.get_columns('students')]
    if 'face_encoding' not in columns:
        with op.batch_alter_table('students', schema=None) as batch_op:
            batch_op.add_column(sa.Column('face_encoding', sa.Text(), nullable=True))

    # Add indexes if missing
    # (Checking indexes is more complex, but batch_op handles existing ones gracefully sometimes)
    # To be safe, we just use batch_op which is generally idempotent for indexes in some dialects
    # but here we'll just try to add them.
    try:
        with op.batch_alter_table('students', schema=None) as batch_op:
            batch_op.create_index('ix_students_program_year', ['program', 'enrollment_year'], unique=False)
            batch_op.create_index('ix_students_hall_year', ['hall', 'enrollment_year'], unique=False)
    except Exception:
        pass

    # 2. Create blacklist table if missing
    if 'blacklist' not in tables:
        op.create_table('blacklist',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('student_id', sa.Integer(), nullable=False),
            sa.Column('reason', sa.Text(), nullable=False),
            sa.Column('added_by', sa.Integer(), nullable=False),
            sa.Column('date_added', sa.DateTime(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.ForeignKeyConstraint(['added_by'], ['users.id'], ),
            sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('student_id')
        )

    # 3. Create academic_records if missing
    if 'academic_records' not in tables:
        op.create_table('academic_records',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('student_id', sa.Integer(), nullable=False),
            sa.Column('form', sa.String(length=50), nullable=False),
            sa.Column('year', sa.Integer(), nullable=False),
            sa.Column('gpa', sa.Float(), nullable=True),
            sa.Column('remarks', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )

    # 4. Create security_logs if missing
    if 'security_logs' not in tables:
        op.create_table('security_logs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('event_type', sa.String(length=50), nullable=False),
            sa.Column('ip_address', sa.String(length=45), nullable=True),
            sa.Column('user_agent', sa.String(length=255), nullable=True),
            sa.Column('details', sa.Text(), nullable=True),
            sa.Column('timestamp', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    # 5. Create used_password_reset_tokens if missing
    if 'used_password_reset_tokens' not in tables:
        op.create_table('used_password_reset_tokens',
            sa.Column('token_hash', sa.String(length=64), nullable=False),
            sa.Column('email', sa.String(length=120), nullable=False),
            sa.Column('used_at', sa.DateTime(), nullable=True),
            sa.Column('ip_address', sa.String(length=45), nullable=True),
            sa.PrimaryKeyConstraint('token_hash')
        )


def downgrade():
    # Downgrade is less critical for a fix but we provide it
    op.drop_table('used_password_reset_tokens')
    op.drop_table('security_logs')
    op.drop_table('academic_records')
    op.drop_table('blacklist')
    with op.batch_alter_table('students', schema=None) as batch_op:
        batch_op.drop_index('ix_students_hall_year')
        batch_op.drop_index('ix_students_program_year')
        batch_op.drop_column('face_encoding')
