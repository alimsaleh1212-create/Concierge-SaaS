"""Create and sync the Postgres role the API uses for request traffic.

The app role is NOSUPERUSER + NOBYPASSRLS, so every RLS policy applies to it.
Its password lives in Vault (inside DATABASE_URL) and is regenerated whenever
Vault is re-initialised, so this runs on every API boot, after migrations:

    python -m app.core.db_roles

Connects as the owner role (SYSTEM_DATABASE_URL). Idempotent.
"""

import asyncio
import re

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _ident(value: str | None, what: str) -> str:
    if not value or not _IDENT_RE.match(value):
        raise RuntimeError(f"Invalid {what} for app role setup: {value!r}")
    return value


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


async def ensure_app_role() -> None:
    settings = get_settings()
    app_url = make_url(settings.DATABASE_URL)
    system_url = make_url(settings.SYSTEM_DATABASE_URL)

    role = _ident(app_url.username, "DATABASE_URL user")
    database = _ident(system_url.database, "database name")
    if role == system_url.username:
        raise RuntimeError(
            "DATABASE_URL and SYSTEM_DATABASE_URL use the same role; the app role "
            "must be separate so RLS is enforced"
        )
    if not app_url.password:
        raise RuntimeError("DATABASE_URL has no password for the app role")

    engine = create_async_engine(settings.SYSTEM_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            exists = (
                await conn.exec_driver_sql(
                    f"SELECT 1 FROM pg_roles WHERE rolname = {_literal(role)}"
                )
            ).scalar()
            verb = "ALTER" if exists else "CREATE"
            # exec_driver_sql: DDL cannot take bind parameters, and text() would
            # misread ':' in the password as a bind marker.
            await conn.exec_driver_sql(
                f"{verb} ROLE {role} WITH LOGIN NOSUPERUSER NOBYPASSRLS "
                f"NOCREATEDB NOCREATEROLE PASSWORD {_literal(app_url.password)}"
            )
            for statement in (
                f"GRANT CONNECT ON DATABASE {database} TO {role}",
                f"GRANT USAGE ON SCHEMA public TO {role}",
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}",
                f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}",
                # Schema bookkeeping is migration-only; audit_log is append-only.
                f"REVOKE ALL ON alembic_version FROM {role}",
                f"REVOKE UPDATE, DELETE ON audit_log FROM {role}",
            ):
                await conn.exec_driver_sql(statement)
        print(f"[db-roles] {verb.lower()}d app role '{role}' (NOBYPASSRLS) and synced grants")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(ensure_app_role())
