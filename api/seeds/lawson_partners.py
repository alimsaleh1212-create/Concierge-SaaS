"""Idempotent seed for LearnSphere demo tenant (Tenant B — online learning platform).

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
from app.rag.ingester import ingest_content

_TENANT_SLUG = "learnsphere"
_ADMIN_EMAIL = "admin@learnsphere.example.com"

_CMS_ITEMS = [
    {
        "title": "About LearnSphere",
        "body": (
            "LearnSphere is an online learning subscription platform offering unlimited access "
            "to over 5,000 courses across technology, business, design, data science, and personal development. "
            "Courses are taught by industry experts and include video lessons, quizzes, projects, and certificates. "
            "Learners can study at their own pace from any device."
        ),
        "content_type": "page",
    },
    {
        "title": "Subscription Plans",
        "body": (
            "Individual Monthly Plan: $19.99/month — full access to all courses, certificates included. "
            "Individual Annual Plan: $149/year (save 38%) — same benefits billed yearly. "
            "Teams Plan: $12/user/month (minimum 5 users) — admin dashboard, progress tracking, and custom learning paths. "
            "All plans include a 7-day free trial. No credit card required to start the trial."
        ),
        "content_type": "product",
    },
    {
        "title": "Cancellation & Refund Policy",
        "body": (
            "You can cancel your subscription at any time from your account settings. "
            "Monthly subscribers retain access until the end of the current billing period. "
            "Annual subscribers can request a prorated refund within 30 days of purchase. "
            "After 30 days, annual plans are non-refundable but you keep access for the full year."
        ),
        "content_type": "faq",
    },
    {
        "title": "Course Certificates",
        "body": (
            "LearnSphere certificates are awarded upon completing all lessons and passing the final assessment (70% pass mark). "
            "Certificates include your name, course title, completion date, and a unique verification URL. "
            "They can be shared directly to LinkedIn or downloaded as a PDF. "
            "Certificates do not expire and remain accessible even after cancelling your subscription."
        ),
        "content_type": "faq",
    },
    {
        "title": "Technical Requirements",
        "body": (
            "LearnSphere works in any modern browser (Chrome, Firefox, Safari, Edge). "
            "Our mobile app is available on iOS 15+ and Android 10+. "
            "Minimum internet speed recommended: 5 Mbps for HD video, 1 Mbps for standard quality. "
            "Videos can be downloaded for offline viewing on mobile (up to 30 videos at a time)."
        ),
        "content_type": "faq",
    },
    {
        "title": "Popular Course Categories",
        "body": (
            "Technology: Python, JavaScript, AWS, machine learning, cybersecurity, and web development. "
            "Business: Project management, entrepreneurship, finance, and marketing. "
            "Design: UI/UX, Figma, Photoshop, motion graphics, and brand identity. "
            "Data Science: SQL, pandas, Tableau, statistics, and AI fundamentals. "
            "New courses are added weekly. Learners can request topics via the course request form."
        ),
        "content_type": "product",
    },
]


async def seed(session: AsyncSession) -> None:
    result = await session.execute(select(Tenant).where(Tenant.slug == _TENANT_SLUG))
    tenant = result.scalar_one_or_none()

    if tenant is None:
        tenant = Tenant(
            name="LearnSphere",
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
            name="LearnSphere Support Widget",
            widget_token_secret=secrets.token_hex(32),
            allowed_origins=["http://localhost:3000"],
            greeting="Hi! Welcome to LearnSphere. How can I help you with your learning journey?",
        ))
        print("[seed] Created widget")

    result = await session.execute(
        select(CmsContent).where(CmsContent.tenant_id == tenant.id, CmsContent.is_deleted == False)  # noqa: E712
    )
    existing_items = result.scalars().all()
    existing_count = len(existing_items)
    if existing_count == 0:
        new_items: list[CmsContent] = []
        for item in _CMS_ITEMS:
            cms = CmsContent(tenant_id=tenant.id, **item)
            session.add(cms)
            new_items.append(cms)
        await session.flush()
        print(f"[seed] Created {len(_CMS_ITEMS)} CMS items")

        for cms in new_items:
            chunks_written = await ingest_content(cms.id, tenant.id, cms.body, session)
            print(f"[seed] Ingested {chunks_written} chunks for '{cms.title}'")
    else:
        print(f"[seed] CMS items already exist ({existing_count}), skipping")

    await session.commit()
    print("[seed] LearnSphere seed complete")


if __name__ == "__main__":
    async def main():
        async with AsyncSessionLocal() as session:
            await seed(session)

    asyncio.run(main())
