"""One-command local dev setup.

Run from the api/ directory with the Python 3.12 venv active:

    python scripts/dev_setup.py

What it does:
  1. Creates all tables (pgvector extension + all ORM models)
  2. Seeds both demo tenants (NovaTech Electronics + LearnSphere)
  3. Embeds all CMS content so RAG actually returns results
  4. Mints a demo visitor JWT for each tenant and prints it

Prerequisites:
  - docker compose -f ../docker-compose.dev.yml up -d (Postgres + Redis running)
  - DEV_MODE=true in ../.env
  - ANTHROPIC_API_KEY and VOYAGE_API_KEY set in ../.env (needed for embedding)
"""
import asyncio
import datetime
import sys
import os

# Locate api/ directory regardless of where the script is invoked from
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))   # api/scripts/
_API_DIR = os.path.dirname(_SCRIPT_DIR)                    # api/
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

import jwt
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
get_settings.cache_clear()  # ensure fresh read of .env, not a stale cached instance
from app.core.database import AsyncSessionLocal, Base
from app.models import *  # noqa: F401,F403 — registers all ORM models with Base
from app.models.tenant import Tenant
from app.models.widget import Widget


async def create_tables() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("[setup] Tables created (idempotent)")


async def run_seeds() -> None:
    from seeds.marios_pizza import seed as seed_novatech
    from seeds.lawson_partners import seed as seed_learnsphere

    async with AsyncSessionLocal() as session:
        await seed_novatech(session)

    async with AsyncSessionLocal() as session:
        await seed_learnsphere(session)


def mint_jwt(tenant_id: str, widget_id: str, jwt_secret: str) -> str:
    payload = {
        "sub": "visitor-demo",
        "tenant_id": tenant_id,
        "widget_id": widget_id,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=8),
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


async def print_demo_tokens() -> None:
    settings = get_settings()
    if not settings.JWT_SECRET:
        print("[setup] JWT_SECRET not set — skipping token minting")
        return

    async with AsyncSessionLocal() as session:
        for slug in ("novatech-electronics", "learnsphere"):
            result = await session.execute(select(Tenant).where(Tenant.slug == slug))
            tenant = result.scalar_one_or_none()
            if tenant is None:
                continue
            result = await session.execute(select(Widget).where(Widget.tenant_id == tenant.id))
            widget = result.scalar_one_or_none()
            if widget is None:
                continue
            token = mint_jwt(str(tenant.id), str(widget.id), settings.JWT_SECRET)
            print(f"\n[setup] Demo JWT for {tenant.name}:")
            print(f"  tenant_id : {tenant.id}")
            print(f"  widget_id : {widget.id}")
            print(f"  token     : {token}")
            print(f"  usage     : Authorization: Bearer {token}")


async def main() -> None:
    print("=== Concierge local dev setup ===")
    settings = get_settings()
    if not settings.DEV_MODE:
        print("ERROR: DEV_MODE is not set. Add DEV_MODE=true to your .env file.")
        sys.exit(1)

    await create_tables()
    await run_seeds()
    await print_demo_tokens()
    print("\n[setup] Done. Start the API with:")
    print("  uvicorn app.main:app --reload --port 8000")


if __name__ == "__main__":
    asyncio.run(main())
