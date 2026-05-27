"""Idempotent seed for NovaTech Electronics demo tenant (Tenant A).

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

_TENANT_SLUG = "novatech-electronics"
_ADMIN_EMAIL = "admin@novatech.example.com"

_CMS_ITEMS = [
    {
        "title": "About NovaTech Electronics",
        "body": (
            "NovaTech Electronics is an online store specialising in consumer electronics, "
            "smart home devices, laptops, smartphones, audio equipment, and accessories. "
            "We carry over 10,000 SKUs from brands including Sony, Samsung, Apple, Dell, Bose, and Anker. "
            "All products come with a minimum 1-year manufacturer warranty."
        ),
        "content_type": "page",
    },
    {
        "title": "Shipping Policy",
        "body": (
            "Standard shipping is free on orders over $50 and takes 3–5 business days. "
            "Express shipping (1–2 business days) is available for $9.99. "
            "Same-day delivery is available in select metro areas for orders placed before 12pm. "
            "International shipping is available to 30+ countries — rates calculated at checkout."
        ),
        "content_type": "faq",
    },
    {
        "title": "Returns & Refunds",
        "body": (
            "We accept returns within 30 days of delivery for most items in original condition. "
            "Opened software, digital downloads, and personalised items are non-returnable. "
            "To start a return, visit your order history and click 'Return Item'. "
            "Refunds are processed within 5–7 business days after we receive the item."
        ),
        "content_type": "faq",
    },
    {
        "title": "Warranty & Repairs",
        "body": (
            "All products sold by NovaTech include the manufacturer's warranty. "
            "Extended warranty plans (1–3 years) are available at checkout for most categories. "
            "For repairs, contact our support team at support@novatech.example.com or call 1-800-668-2832. "
            "We partner with authorised service centres in 50+ cities."
        ),
        "content_type": "faq",
    },
    {
        "title": "Top Product Categories",
        "body": (
            "Laptops & Computers: Gaming laptops, ultrabooks, desktops, and monitors. "
            "Smartphones & Tablets: Latest iPhone, Samsung Galaxy, iPad, and Android models. "
            "Audio: Noise-cancelling headphones, earbuds, soundbars, and hi-fi speakers. "
            "Smart Home: Smart speakers, security cameras, robot vacuums, and lighting. "
            "Accessories: Cables, chargers, cases, screen protectors, and storage."
        ),
        "content_type": "product",
    },
    {
        "title": "Payment & Security",
        "body": (
            "We accept Visa, Mastercard, American Express, PayPal, Apple Pay, and Google Pay. "
            "Buy Now Pay Later is available via Klarna (0% interest for 3 months on orders over $200). "
            "All transactions are encrypted with TLS 1.3. We do not store card numbers."
        ),
        "content_type": "faq",
    },
]


async def seed(session: AsyncSession) -> None:
    result = await session.execute(select(Tenant).where(Tenant.slug == _TENANT_SLUG))
    tenant = result.scalar_one_or_none()

    if tenant is None:
        tenant = Tenant(
            name="NovaTech Electronics",
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
            name="NovaTech Support Widget",
            widget_token_secret=secrets.token_hex(32),
            allowed_origins=["http://localhost:3000"],
            greeting="Hi! Welcome to NovaTech Electronics. How can I help you today?",
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
    print("[seed] NovaTech Electronics seed complete")


if __name__ == "__main__":
    async def main():
        async with AsyncSessionLocal() as session:
            await seed(session)

    asyncio.run(main())
