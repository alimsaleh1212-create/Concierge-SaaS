"""Health endpoint router."""

from fastapi import APIRouter

from app.nemo_runtime import get_nemo_runtime


router = APIRouter()


@router.get("/health")
def health() -> dict[str, list[str] | str]:
    return {
        "status": "ok",
        "rails_loaded": ["platform_rails", "tenant_rails"],
        "nemo_runtime": get_nemo_runtime().status,
    }
