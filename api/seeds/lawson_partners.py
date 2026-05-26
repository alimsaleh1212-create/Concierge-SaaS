"""Idempotent seed for Lawson & Partners demo tenant (DECISIONS.md D-005).

Safe to run multiple times — skips rows that already exist.
"""
import asyncio
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.cms_content import CmsContent
from app.models.tenant import Tenant
from app.models.user import User
from app.models.widget import Widget

_TENANT_SLUG = "lawson-partners"
_ADMIN_EMAIL = "admin@lawsonpartners.example.com"

_CMS_ITEMS = [
    {
        "title": "Practice Areas",
        "body": (
            "Lawson & Partners specialises in corporate law, mergers & acquisitions, "
            "employment law, intellectual property, and real estate transactions. "
            "Our team of 25 attorneys has over 200 years of combined experience."
        ),
        "content_type": "page",
    },
    {
        "title": "Our Team",
        "body": (
            "Our founding partners are Sarah Lawson (Corporate, M&A) and James Lawson (Employment, IP). "
            "Senior associates include Maria Chen (Real Estate), David Patel (Litigation), "
            "and Anya Kowalski (Contracts). All attorneys are bar-certified in the state of New York."
        ),
        "content_type": "page",
    },
    {
        "title": "Consultation FAQ",
        "body": (
            "How do I book a consultation? Call (212) 555-0100 or use our online booking form. "
            "Initial consultations are 30 minutes and are free of charge. "
            "Bring any relevant documents or contracts to your first meeting."
        ),
        "content_type": "faq",
    },
    {
        "title": "Fees & Billing",
        "body": (
            "We offer hourly billing ($350–$650/hr depending on attorney), fixed-fee packages "
            "for standard contracts and incorporations, and contingency arrangements for select "
            "litigation matters. All estimates provided in writing before engagement."
        ),
        "content_type": "faq",
    },
    {
        "title": "Contact & Office",
        "body": (
            "Office: 500 Fifth Avenue, Suite 1800, New York, NY 10110. "
            "Hours: Monday–Friday 9am–6pm. "
            "Email: info@lawsonpartners.example.com. Phone: (212) 555-0100."
        ),
        "content_type": "page",
    },
]


async def seed(session: AsyncSession) -> None:
    result = await session.execute(select(Tenant).where(Tenant.slug == _TENANT_SLUG))
    tenant = result.scalar_one_or_none()

    if tenant is None:
        tenant = Tenant(
            name="Lawson & Partners",
            slug=_TENANT_SLUG,
            allowed_origins=["http://localhost:3000"],
        )
        session.add(tenant)
        await session.flush()
        print(f"[seed] Created tenant: {_TENANT_SLUG} ({tenant.id})")
    else:
        print(f"[seed] Tenant already exists: {_TENANT_SLUG}")

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

    result = await session.execute(select(Widget).where(Widget.tenant_id == tenant.id))
    if result.scalar_one_or_none() is None:
        session.add(Widget(
            tenant_id=tenant.id,
            name="Lawson & Partners Chat",
            widget_token_secret=secrets.token_hex(32),
            allowed_origins=["http://localhost:3000"],
            greeting="Welcome to Lawson & Partners. How can we assist you today?",
        ))
        print("[seed] Created widget")

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
    print("[seed] Lawson & Partners seed complete")


if __name__ == "__main__":
    async def main():
        async with AsyncSessionLocal() as session:
            await seed(session)

    asyncio.run(main())
