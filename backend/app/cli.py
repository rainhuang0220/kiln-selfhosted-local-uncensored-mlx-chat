"""Local owner bootstrap. Do not use this over the public internet."""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from app.config import settings
from app.db import init_db
from app.services import accounts


def create_owner(username: str, password: str) -> None:
    init_db(settings.sqlite_path)
    if accounts.user_count() > 0:
        raise SystemExit("an owner already exists; refuse to create another via bootstrap")
    user = accounts.ensure_bootstrap(username, password)
    if user is None:
        raise SystemExit("bootstrap refused")
    print(f"owner created username={user.username} role={user.role}")
    print("legacy null-owner conversations/memories/media assigned to this owner")


def create_token(username: str, name: str) -> None:
    init_db(settings.sqlite_path)
    row = accounts.get_conn().execute(
        "SELECT id FROM users WHERE username=?",
        (accounts.normalize_username(username),),
    ).fetchone()
    if row is None:
        raise SystemExit("user not found")
    token = accounts.create_api_token(row["id"], name=name)
    print(token)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    owner = sub.add_parser("create-owner", help="create the first owner on this machine")
    owner.add_argument("--username", required=True)
    token = sub.add_parser("create-api-token", help="create a revocable API bearer token")
    token.add_argument("--username", required=True)
    token.add_argument("--name", default="cli")
    chpw = sub.add_parser("change-password", help="change a local account password and revoke sessions")
    chpw.add_argument("--username", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "create-owner":
        password = os.environ.get("KILN_BOOTSTRAP_PASSWORD") or getpass.getpass("owner password: ")
        create_owner(args.username, password)
        return
    if args.cmd == "create-api-token":
        create_token(args.username, args.name)
        return
    if args.cmd == "change-password":
        init_db(settings.sqlite_path)
        current = os.environ.get("KILN_CURRENT_PASSWORD") or getpass.getpass("current password: ")
        new = os.environ.get("KILN_NEW_PASSWORD") or getpass.getpass("new password: ")
        try:
            accounts.change_password(args.username, current, new)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print("password updated; all sessions revoked")
        return


if __name__ == "__main__":
    main(sys.argv[1:])
