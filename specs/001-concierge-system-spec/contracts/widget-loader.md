# Contract: Widget Loader & postMessage Protocol

**Owner**: D
**Widget bundle served from**: MinIO at `/widget-bundle/index.js` (CDN-style)
**Loader script served from**: API at `GET /widget.js`

---

## Embed Flow

Host site pastes one tag (no other setup required):

```html
<script src="https://api.concierge.example/widget.js"
        data-widget-id="550e8400-e29b-41d4-a716-446655440000">
</script>
```

### Loader Script (`/widget.js`) Behaviour

1. Reads `data-widget-id` from the `<script>` element
2. Reads `window.location.origin` as the current origin
3. Calls `POST /auth/widget-token` with `{ widget_id, origin }`
   - On 403: logs to console ("Widget not allowed on this origin") and stops
   - On any other error: logs and stops — no fallback UI
4. On success: receives `{ token, expires_in }`
5. Creates an `<iframe>` pointing to the MinIO-hosted bundle URL
   - Passes `token` to the iframe via `postMessage` after load
6. Injects the iframe into `document.body` with a fixed position/style

The loader is ~5 KB (vanilla JS, no framework), served with `Cache-Control: no-cache`
so changes propagate immediately.

---

## postMessage Protocol (loader → iframe)

### Initialise
```json
{
  "type": "CONCIERGE_INIT",
  "token": "eyJ...",
  "widget_id": "uuid"
}
```
Sent by loader to iframe after iframe `load` event.

### Send message (iframe → loader → API)
The iframe sends chat messages directly to the API (not via the loader) using the
token from `CONCIERGE_INIT`.

---

## Widget Bundle API calls

All calls from within the iframe use:
```
POST /chat/messages
Authorization: Bearer <token>
Content-Type: application/json
```

Token is stored in React state (never in localStorage — XSS risk).

---

## Bundle Size Budget

| Artifact | Budget |
|----------|--------|
| Widget bundle (gzipped) | < 50 KB |
| Loader script (`/widget.js`) | < 5 KB |

CI fails if gzipped bundle exceeds 50 KB.

---

## CORS + CSP Configuration

The API serves these headers on every response to widget origins:

```
Access-Control-Allow-Origin: <origin> (if in allowed_origins for this tenant)
Content-Security-Policy: frame-ancestors 'self' https://example.com
```

These are defence-in-depth only. The signed token + server-side origin check is the
actual auth boundary. A `curl` with a missing or stale token gets 401 regardless of
origin header.
