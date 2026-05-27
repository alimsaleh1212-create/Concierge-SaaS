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
from app.core.config import get_settings
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


def _decode_widget_jwt(token: str) -> dict:
    """Decode widget JWT and return claims. Raises HTTP 401 on failure."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
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
    # 1. Verify widget JWT → extract tenant_id, widget_id, session_id
    token = _extract_bearer(request)
    claims = _decode_widget_jwt(token)
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
        # 3. Guardrails input check
        if await guardrails_client.check_input(body.content, tenant_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message blocked by platform policy.")

        # 4. Load conversation via JWT session_id — client cannot spoof a different session
        conv_repo = ConversationRepository(session)
        conversation = await conv_repo.get_by_session(session_id, tenant_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

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
        if await guardrails_client.check_output(result.response, tenant_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Response blocked by platform policy.")

        # 8. PII-redact response
        safe_response = redaction.redact(result.response)

        # 9. Persist messages
        session.add(Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            role="user",
            content=body.content,
        ))
        session.add(Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            role="assistant",
            content=safe_response,
        ))
        await session.flush()

        # 10. Update Redis session history
        await append_to_session(tenant_id, conversation.id, "user", body.content)
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
