import json
import os

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.title("Guardrails")

token = st.session_state.get("access_token")
role = st.session_state.get("role")
if not token:
    st.warning("Please log in from the main page.")
    st.stop()
if role != "tenant_admin":
    st.error("Guardrails require tenant_admin role.")
    st.stop()

headers = {"Authorization": f"Bearer {token}"}

response = requests.get(f"{API_BASE_URL}/admin/widgets", headers=headers, timeout=10)
response.raise_for_status()
widgets = response.json().get("widgets", [])

if not widgets:
    st.info("No widgets found yet.")
    st.stop()

widget_options = {f"{w.get('name')} ({w.get('id')})": w for w in widgets}
selected_label = st.selectbox("Widget", list(widget_options.keys()))
selected_widget = widget_options[selected_label]

current_config = selected_widget.get("theme_config") or {}
rails_config = current_config.get("tenant_rails") or {}

allowed_topics = st.text_area(
    "Allowed topics (comma separated)",
    value=", ".join(rails_config.get("allowed_topics") or []),
)
blocked_topics = st.text_area(
    "Blocked topics (comma separated)",
    value=", ".join(rails_config.get("blocked_topics") or []),
)
refusal_tone = st.selectbox(
    "Refusal tone",
    ["neutral", "firm", "empathetic"],
    index=["neutral", "firm", "empathetic"].index(rails_config.get("refusal_tone", "neutral")),
)

if st.button("Save Guardrails"):
    updated_config = {
        **current_config,
        "tenant_rails": {
            "allowed_topics": [t.strip() for t in allowed_topics.split(",") if t.strip()],
            "blocked_topics": [t.strip() for t in blocked_topics.split(",") if t.strip()],
            "refusal_tone": refusal_tone,
        },
    }
    patch_response = requests.patch(
        f"{API_BASE_URL}/admin/widgets/{selected_widget['id']}",
        headers={**headers, "Content-Type": "application/json"},
        json={"theme_config": updated_config},
        timeout=10,
    )
    if patch_response.ok:
        st.success("Guardrails updated")
        st.rerun()
    else:
        st.error("Failed to update guardrails")

st.subheader("Current Guardrails JSON")
st.code(json.dumps(rails_config, indent=2))
