"""Guardrails input and output endpoint router."""

from fastapi import APIRouter, Depends

from app.constants import SAFE_REFUSAL
from app.schemas import (
    RailsInputRequest,
    RailsInputResponse,
    RailsOutputRequest,
    RailsOutputResponse,
)
from app.security import _require_service_token
from app.services.platform_checks import check_platform_input, check_platform_output
from app.services.tenant_checks import check_tenant_input


router = APIRouter()


@router.post(
    "/rails/input",
    response_model=RailsInputResponse,
    dependencies=[Depends(_require_service_token)],
)
def check_input(request: RailsInputRequest) -> RailsInputResponse:
    platform_result = check_platform_input(request.content)
    if platform_result:
        reason, refusal_message = platform_result
        return RailsInputResponse(
            allowed=False,
            modified_content=None,
            reason=reason,
            refusal_message=refusal_message,
        )

    reason = check_tenant_input(request)
    if reason:
        return RailsInputResponse(
            allowed=False,
            modified_content=None,
            reason=reason,
            refusal_message=SAFE_REFUSAL,
        )

    return RailsInputResponse(allowed=True)


@router.post(
    "/rails/output",
    response_model=RailsOutputResponse,
    dependencies=[Depends(_require_service_token)],
)
def check_output(request: RailsOutputRequest) -> RailsOutputResponse:
    platform_result = check_platform_output(request.content)
    if platform_result:
        reason, refusal_message, modified_content = platform_result
        return RailsOutputResponse(
            allowed=False,
            modified_content=modified_content,
            reason=reason,
            refusal_message=refusal_message,
        )

    return RailsOutputResponse(allowed=True)
