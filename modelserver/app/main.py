from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from .classifier import predict
from .startup import verify_model_artifact


MODEL_TYPE = "logistic_regression"
SERVICE_TOKEN_ENV = "MODELSERVER_SERVICE_TOKEN"


class ClassifyRequest(BaseModel):
    text: str = Field(min_length=1)


class ClassifyResponse(BaseModel):
    label: str
    confidence: float


class HealthResponse(BaseModel):
    status: str
    model: str
    artifact_sha256: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.artifact_sha256 = verify_model_artifact()
    yield


app = FastAPI(title="Concierge Modelserver", lifespan=lifespan)


def require_service_token(authorization: str | None = Header(default=None)) -> None:
    expected_token = os.getenv(SERVICE_TOKEN_ENV)

    # Local development can call the modelserver without a bearer token. Deployed
    # environments must set MODELSERVER_SERVICE_TOKEN to enforce service auth.
    if not expected_token:
        return

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid service token",
        )


@app.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        model=MODEL_TYPE,
        artifact_sha256=request.app.state.artifact_sha256,
    )


@app.post(
    "/classify",
    response_model=ClassifyResponse,
    dependencies=[Depends(require_service_token)],
)
def classify(payload: ClassifyRequest) -> ClassifyResponse:
    label, confidence = predict(payload.text)
    return ClassifyResponse(label=label, confidence=confidence)
