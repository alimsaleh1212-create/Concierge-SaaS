# API Contract: Modelserver (port 8001)

**Owner**: C
**Base URL**: `http://modelserver:8001` (Docker Compose internal network)
**Auth**: `Authorization: Bearer <MODELSERVER_SERVICE_TOKEN>` (from Vault)

The modelserver refuses to start if the artifact SHA-256 does not match `model_card.md`.

---

## POST /classify

Classify an inbound visitor message into `sales`, `support`, or `spam`.

**Request**
```json
{ "text": "I'd like to get a quote for your premium legal package" }
```

**Response 200**
```json
{ "label": "sales", "confidence": 0.94 }
```

**label values**: `"sales"` · `"support"` · `"spam"`
**confidence**: float in [0.0, 1.0] — sigmoid output for classical; softmax for DL/LLM

**Error responses**:
- 401 missing or invalid service token
- 422 missing `text` field or empty string
- 503 model not loaded (SHA-256 mismatch at boot — container exits, so 503 means restart in progress)

---

## GET /health

```json
{ "status": "ok", "model": "classical|onnx", "artifact_sha256": "abc123..." }
```

No auth required. Used by Docker Compose healthcheck.

---

## Startup Boot Check

On container start, `startup.py` does:

```python
import hashlib, sys
from pathlib import Path

def verify_artifact(artifact_path: str, expected_sha256: str):
    data = Path(artifact_path).read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        print(f"FATAL: artifact SHA-256 mismatch. Expected {expected_sha256}, got {actual}")
        sys.exit(1)
```

The `expected_sha256` is read from `model_card.md` at the path pinned in config.
