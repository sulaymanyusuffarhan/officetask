"""Administrative commands; run only on the server with its configured environment."""
import argparse
from getpass import getpass
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.roles import ADMIN, ROLE_NAMES
from app.core.security import hash_password
from app.db.session import engine
from app.models.models import Department, Role, Shift, User


def migrate() -> None:
    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / "alembic.ini"))
    command.upgrade(config, "head")


def seed() -> None:
    with Session(engine) as db:
        for role_id, name in ROLE_NAMES.items():
            if not db.get(Role, role_id):
                db.add(Role(id=role_id, name=name))
        if not db.scalar(select(Department).limit(1)):
            db.add(Department(name="General"))
        if not db.scalar(select(Shift).limit(1)):
            db.add(Shift(name="Morning", start_time="08:00", end_time="16:00"))
            db.add(Shift(name="Evening", start_time="16:00", end_time="23:00"))
        db.commit()


def create_admin(username: str | None = None) -> None:
    username = username or input("Administrator username: ").strip()
    name = input("Administrator full name: ").strip()
    password = getpass("New password (12+ characters): ")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords did not match")
    with Session(engine) as db:
        if db.scalar(select(User).where(User.username == username)):
            raise SystemExit("That username already exists")
        user = User(username=username, full_name=name, password_hash=hash_password(password), role_id=ADMIN)
        db.add(user)
        db.commit()
        print(f"Created administrator account {username!r}. Keep this account for system administration; it does not gain business approval rights.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Office Task system administration")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Apply migrations and seed standard roles/shifts")
    create = sub.add_parser("create-admin", help="Create a system-administrator account")
    create.add_argument("--username")
    args = parser.parse_args()
    if args.command == "init-db":
        migrate()
        seed()
        print("Database migrations applied and role catalogue seeded.")
    elif args.command == "create-admin":
        create_admin(args.username)


if __name__ == "__main__":
    main()
