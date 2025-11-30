from alembic.config import Config
from alembic import command

alembic_cfg = Config("alembic.ini")

# create migration automatically
command.revision(alembic_cfg, message="Add email to user_profile", autogenerate=True)

# upgrade database
command.upgrade(alembic_cfg, "head")
