# API Contract: Modelserver

**Owner**: C  
**Service name**: `modelserver`  
**Port**: `8001`  
**Base URL inside Docker Compose**: `http://modelserver:8001`  
**Auth**: `Authorization: Bearer <MODELSERVER_SERVICE_TOKEN>` from Vault  

The modelserver is responsible for serving the trained visitor-message classifier over HTTP.

The classifier is used by the main API/router to classify inbound visitor messages before deciding whether the message should go to RAG, lead capture, escalation, spam handling, or the agent.

The modelserver must be a lean serving container:

- Classical ML model: served with `scikit-learn` + `joblib`
- DL model: served with `onnxruntime`
- No `torch`
- No `transformers`
- No training code inside the serving container

The modelserver refuses to start if the classifier artifact SHA-256 does not match the SHA-256 pinned in `model_card.md`.

---

## POST `/classify`

Classify an inbound visitor message into one of the Concierge router labels.

### Request

```json
{
  "text": "I want to know your pricing and talk to someone about a plan"
}
```

### Response 200

```json
{
  "label": "sales_or_leads",
  "confidence": 0.94
}
```

---

## Label Values

The modelserver must return exactly one of these labels:

```text
faq
support
sales_or_leads
human_request
spam
other
```

### Label Meaning

| Label | Meaning | Expected Router Action |
|---|---|---|
| `faq` | The visitor is asking a simple informational question. | Use `rag_search` over the current tenant’s CMS content. |
| `support` | The visitor needs help with an issue, account, order, refund, payment, or similar problem. | Use `rag_search`, or send to the agent if the issue is complex or confidence is low. |
| `sales_or_leads` | The visitor shows buying, signup, order, pricing, subscription, or lead intent. | Use `capture_lead`, or ask for missing contact details first. |
| `human_request` | The visitor explicitly asks for a human, agent, representative, or customer service. | Use `escalate`. |
| `spam` | The message is junk, scam, promotional spam, or clearly abusive spam. | Drop/refuse. Do not send to the LLM. Do not store as a lead. |
| `other` | The message does not clearly fit the fixed router labels. | Send to the agent or refuse as out-of-scope depending on guardrails/router policy. |

---

## Dataset Label Sources

The classifier dataset is built from multiple public datasets and mapped into the project router labels.

| Source | Used For | Project Labels |
|---|---|---|
| Bitext customer-support dataset | Customer-support and business intent examples | `faq`, `support`, `sales_or_leads`, `human_request` |
| SMS Spam Collection | Spam examples only | `spam` |
| CLINC OOS | Explicit out-of-scope examples only | `other` |

Important: CLINC is used only for rows where the original CLINC intent is `oos`.  
We do not label all CLINC rows as `other`.

Important: SMS ham messages are not used as `other`.  
Only SMS rows labeled `spam` are used.

---

## Confidence

`confidence` is a float between `0.0` and `1.0`.

For the shipped classical ML model, confidence is:

```text
max(model.predict_proba(text))
```

For an ONNX/DL model, confidence is the softmax probability of the predicted class.

The router may use a confidence threshold. For example:

```text
if confidence < threshold:
    send to agent
else:
    use the direct workflow for the predicted label
```

The exact threshold is defined in the router/evaluation configuration, not inside the modelserver contract.

---

## Error Responses

### 401 Unauthorized

Returned when the service token is missing or invalid.

```json
{
  "detail": "Missing or invalid service token"
}
```

### 422 Validation Error

Returned when the request is missing the `text` field or the text is empty.

```json
{
  "detail": "text must be a non-empty string"
}
```

### 503 Service Unavailable

Returned only if the modelserver process is running but the classifier model is not loaded.

```json
{
  "detail": "Model not loaded"
}
```

Note: if the artifact SHA-256 mismatches during startup, the container should exit. In that case, Docker Compose healthcheck should fail instead of the API returning a normal 503.

---

## GET `/health`

No auth required. Used by Docker Compose healthcheck.

### Response 200

```json
{
  "status": "ok",
  "model_type": "classical",
  "artifact_sha256": "abc123..."
}
```

`model_type` must be one of:

```text
classical
onnx
```

---

## Startup Boot Check

On startup, the modelserver verifies that the model artifact matches the SHA-256 pinned in `model_card.md`.

If the actual hash does not match the expected hash, the modelserver must exit and refuse to serve predictions.

Example boot check:

```python
import hashlib
import sys
from pathlib import Path


def verify_artifact(artifact_path: str, expected_sha256: str) -> None:
    data = Path(artifact_path).read_bytes()
    actual = hashlib.sha256(data).hexdigest()

    if actual != expected_sha256:
        print(
            f"FATAL: artifact SHA-256 mismatch. "
            f"Expected {expected_sha256}, got {actual}"
        )
        sys.exit(1)
```

The expected SHA-256 is read from `model_card.md`.

Example environment variables:

```text
MODEL_CARD_PATH=/app/artifacts/model_card.md
MODEL_ARTIFACT_PATH=/app/artifacts/concierge_intent_classifier.joblib
```

---

## Model Card Requirements

`model_card.md` must include:

- classifier task
- final labels
- dataset sources
- train/validation/test split
- dataset file hashes
- classical ML result
- DL/ONNX result
- LLM zero-shot baseline result
- chosen production model
- reason for choosing the production model
- model artifact SHA-256

---

## Service-to-Service Authentication

The main API must call the modelserver with a service token from Vault.

Example request header:

```http
Authorization: Bearer <MODELSERVER_SERVICE_TOKEN>
```

The modelserver must reject calls with a missing or invalid token.

This service is internal to Docker Compose, but internal networking is not treated as authentication.

---

## Responsibility Boundary

The modelserver only classifies messages.

It does not:

- run the router
- call the LLM
- call RAG
- capture leads
- escalate conversations
- apply tenant isolation
- read tenant CMS content

The main API/router owns those decisions.

The modelserver returns:

```json
{
  "label": "faq",
  "confidence": 0.91
}
```

Then the router decides the next action.