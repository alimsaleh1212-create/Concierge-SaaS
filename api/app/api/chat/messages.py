import uuid
import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import guardrails_client, redaction
from app.agent.agent import TenantContext
from app.agent.memory import append_to_session, get_session_history
from app.agent.router import route
from app.core.database import get_db
from app.models.message import Message
from app.repositories.conversation_repo import ConversationRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    content: str


class ChatResponse(BaseModel):
    session_id: str
    conversation_id: uuid.UUID
    response: str
    tool_used: str | None = None
    escalated: bool = False
    lead_captured: bool = False


def _decode_widget_jwt_unverified(token: str) -> dict:
    """Decode widget JWT without signature verification to extract widget_id."""
    try:
        return jwt.decode(token, options={"verify_signature": False}, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid widget token") from exc


async def _verify_widget_jwt(token: str, session: AsyncSession) -> tuple[dict, dict]:
    """Look up the widget's own secret then fully verify the token.
    Returns (claims, tenant_rails) where tenant_rails is the widget's guardrails config.
    """
    from sqlalchemy import select
    from app.models.widget import Widget

    claims = _decode_widget_jwt_unverified(token)
    widget_id = claims.get("widget_id")
    if not widget_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid widget token")

    result = await session.execute(
        select(Widget.widget_token_secret, Widget.theme_config).where(
            Widget.id == widget_id, Widget.is_active == True, Widget.is_deleted == False  # noqa: E712
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid widget token")

    secret, theme_config = row
    tenant_rails = (theme_config or {}).get("tenant_rails", {})

    try:
        return jwt.decode(token, secret, algorithms=["HS256"]), tenant_rails
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid widget token") from exc


def _extract_bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return auth[len("Bearer "):]


@router.post("/messages", response_model=ChatResponse)
async def post_message(
    request: Request,
    body: ChatRequest,
    session: AsyncSession = Depends(get_db),
) -> ChatResponse:
    # 1. Verify widget JWT → extract tenant_id, widget_id, session_id + widget tenant_rails
    token = _extract_bearer(request)
    claims, tenant_rails = await _verify_widget_jwt(token, session)
    tenant_id = uuid.UUID(claims["tenant_id"])
    widget_id = uuid.UUID(claims["widget_id"])
    session_id: str = claims["session_id"]

    # 2. RLS is set by get_db dependency via tenant_id path param; here we call directly
    from sqlalchemy import text
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )

    try:
        # 3. Load or create conversation — must happen before guardrails so we have conversation_id
        from app.models.conversation import Conversation
        conv_repo = ConversationRepository(session)
        conversation = await conv_repo.get_by_session(session_id, tenant_id)
        if conversation is None:
            conversation = Conversation(
                tenant_id=tenant_id,
                widget_id=widget_id,
                session_id=session_id,
            )
            session.add(conversation)
            await session.flush()

        # 4. Guardrails input check — now we have conversation_id and tenant_rails
        if await guardrails_client.check_input(body.content, tenant_id, conversation.id, tenant_rails):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message blocked by platform policy.")

        history = await get_session_history(tenant_id, conversation.id)

        # 5. Build tenant context
        tenant_ctx = TenantContext(
            tenant_id=tenant_id,
            widget_id=widget_id,
            conversation_id=conversation.id,
            tenant_name=claims.get("tenant_name", "our business"),
            persona=claims.get("persona", "a helpful customer service agent"),
            allowed_topics=claims.get("allowed_topics", "questions related to our business"),
            visitor_ip=request.client.host if request.client else None,
        )

        # 6. Route → workflow or agent
        result = await route(
            message=body.content,
            messages=history,
            tenant_ctx=tenant_ctx,
            session=session,
        )

        # 7. Guardrails output check
        if await guardrails_client.check_output(result.response, tenant_id, conversation.id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Response blocked by platform policy.")

        # 8. PII-redact both user input and assistant response before any persistence
        safe_user_content = redaction.redact(body.content).text
        safe_response = redaction.redact(result.response).text

        # 9. Persist messages (redacted content only — never raw PII in DB)
        session.add(Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            role="user",
            content=safe_user_content,
        ))
        session.add(Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            role="assistant",
            content=safe_response,
        ))
        await session.flush()

        # 10. Update Redis session history (redacted content only)
        await append_to_session(tenant_id, conversation.id, "user", safe_user_content)
        await append_to_session(tenant_id, conversation.id, "assistant", safe_response)

        await session.commit()

        return ChatResponse(
            session_id=session_id,
            conversation_id=conversation.id,
            response=safe_response,
            tool_used=result.tool_used,
            escalated=result.escalated,
            lead_captured=result.lead_captured,
        )

    finally:
        # Reset RLS — always, even on error
        await session.execute(
            text("SELECT set_config('app.tenant_id', '', true)")
        )
