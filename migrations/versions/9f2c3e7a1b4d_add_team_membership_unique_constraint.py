"""enforce unique registered player per team

Revision ID: 9f2c3e7a1b4d
Revises: d67dc0c66fa3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9f2c3e7a1b4d"
down_revision: Union[str, Sequence[str], None] = "d67dc0c66fa3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fail loudly rather than silently choosing a duplicate if bad data already exists.
    bind = op.get_bind()
    duplicates = bind.execute(sa.text("""
        SELECT team_id, player_user_id, COUNT(*) AS n
        FROM team_memberships
        WHERE player_user_id IS NOT NULL
        GROUP BY team_id, player_user_id
        HAVING COUNT(*) > 1
    """)).fetchall()
    if duplicates:
        raise RuntimeError(
            "Cannot add uq_team_membership_team_player: duplicate registered players "
            f"already exist for team/player pairs: {duplicates}"
        )
    with op.batch_alter_table("team_memberships") as batch_op:
        batch_op.create_unique_constraint(
            "uq_team_membership_team_player",
            ["team_id", "player_user_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("team_memberships") as batch_op:
        batch_op.drop_constraint("uq_team_membership_team_player", type_="unique")
