"""Idempotent seed for Mario's Pizza demo tenant (DECISIONS.md D-005).

Safe to run multiple times — skips rows that already exist.
"""
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.cms_content import CmsContent
from app.models.tenant import Tenant
from app.models.user import User
from app.models.widget import Widget

import secrets

_TENANT_SLUG = "marios-pizza"
_ADMIN_EMAIL = "admin@mariospizza.example.com"

_CMS_ITEMS = [
    {
        "title": "Our Menu",
        "body": (
            "Mario's Pizza offers a wide selection of handcrafted pizzas, pastas, and salads. "
            "Our signature dishes include the Margherita (tomato, mozzarella, basil), "
            "the Pepperoni Feast, and the Veggie Supreme with seasonal vegetables. "
            "All pizzas are available in 10\", 12\", and 16\" sizes."
        ),
        "content_type": "page",
    },
    {
        "title": "Opening Hours",
        "body": (
            "We are open Monday–Thursday 11am–10pm, Friday–Saturday 11am–11pm, "
            "and Sunday 12pm–9pm. We are closed on Thanksgiving and Christmas Day."
        ),
        "content_type": "faq",
    },
    {
        "title": "Delivery FAQ",
        "body": (
            "Do you deliver? Yes! We deliver within a 5-mile radius. Delivery takes 30–45 minutes. "
            "Minimum order is $15. We use our own drivers — no third-party apps. "
            "Delivery fee is $3.99. Free delivery on orders over $40."
        ),
        "content_type": "faq",
    },
    {
        "title": "Our Location",
        "body": (
            "Find us at 123 Olive Street, Downtown. We have free parking in the lot behind the restaurant. "
            "We're two blocks from the Central Metro station (Blue Line)."
        ),
        "content_type": "page",
    },
    {
        "title": "Weekly Specials",
        "body": (
            "Tuesday: Buy one pizza, get one 50% off. "
            "Wednesday: Family meal deal — large pizza + 2 sides + 4 drinks for $39.99. "
            "Friday: Happy Hour 3–6pm, all draft beers $4."
        ),
        "content_type": "product",
    },
]


async def seed(session: AsyncSession) -> None:
    # Idempotency check
    result = await session.execute(select(Tenant).where(Tenant.slug == _TENANT_SLUG))
    tenant = result.scalar_one_or_none()

    if tenant is None:
        tenant = Tenant(
            name="Mario's Pizza",
            slug=_TENANT_SLUG,
            allowed_origins=["http://localhost:3000"],
        )
        session.add(tenant)
        await session.flush()
        print(f"[seed] Created tenant: {_TENANT_SLUG} ({tenant.id})")
    else:
        print(f"[seed] Tenant already exists: {_TENANT_SLUG}")

    # Admin user
    result = await session.execute(select(User).where(User.email == _ADMIN_EMAIL))
    if result.scalar_one_or_none() is None:
        session.add(User(
            tenant_id=tenant.id,
            email=_ADMIN_EMAIL,
            hashed_password=get_password_hash("demo-password-change-me"),
            role="tenant_admin",
            is_active=True,
        ))
        print(f"[seed] Created admin user: {_ADMIN_EMAIL}")

    # Widget
    result = await session.execute(select(Widget).where(Widget.tenant_id == tenant.id))
    if result.scalar_one_or_none() is None:
        session.add(Widget(
            tenant_id=tenant.id,
            name="Mario's Chat Widget",
            widget_token_secret=secrets.token_hex(32),
            allowed_origins=["http://localhost:3000"],
            greeting="Hi! Welcome to Mario's Pizza. How can I help you today?",
        ))
        print("[seed] Created widget")

    # CMS items
    result = await session.execute(
        select(CmsContent).where(CmsContent.tenant_id == tenant.id, CmsContent.is_deleted == False)  # noqa: E712
    )
    existing_count = len(result.scalars().all())
    if existing_count == 0:
        for item in _CMS_ITEMS:
            session.add(CmsContent(tenant_id=tenant.id, **item))
        print(f"[seed] Created {len(_CMS_ITEMS)} CMS items")
    else:
        print(f"[seed] CMS items already exist ({existing_count}), skipping")

    await session.commit()
    print("[seed] Mario's Pizza seed complete")


if __name__ == "__main__":
    async def main():
        async with AsyncSessionLocal() as session:
            await seed(session)

    asyncio.run(main())
