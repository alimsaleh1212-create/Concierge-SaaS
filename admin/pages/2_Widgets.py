import json
import os

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.title("Widgets")

token = st.session_state.get("access_token")
role = st.session_state.get("role")
if not token:
    st.warning("Please log in from the main page.")
    st.stop()
if role != "tenant_admin":
    st.error("Widgets require tenant_admin role.")
    st.stop()

headers = {"Authorization": f"Bearer {token}"}

response = requests.get(f"{API_BASE_URL}/admin/widgets", headers=headers, timeout=10)
response.raise_for_status()
widgets = response.json().get("widgets", [])

st.subheader("Create Widget")
with st.form("create_widget"):
    name = st.text_input("Name")
    greeting = st.text_input("Greeting")
    allowed = st.text_input("Allowed origins (comma separated)")
    theme_text = st.text_area("Theme config (JSON)", value="{}")
    submitted = st.form_submit_button("Create")

if submitted:
    try:
        payload = {
            "name": name,
            "greeting": greeting or None,
            "allowed_origins": [o.strip() for o in allowed.split(",") if o.strip()],
            "theme_config": json.loads(theme_text) if theme_text else {},
        }
        create_response = requests.post(
            f"{API_BASE_URL}/admin/widgets",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        create_response.raise_for_status()
        st.success("Widget created")
        st.rerun()
    except json.JSONDecodeError:
        st.error("Theme config must be valid JSON")
    except requests.HTTPError:
        st.error("Failed to create widget")

st.subheader("Existing Widgets")
for widget in widgets:
    with st.expander(f"{widget.get('name')} ({widget.get('id')})"):
        edit_greeting = st.text_input(
            "Greeting",
            value=widget.get("greeting") or "",
            key=f"greet-{widget['id']}",
        )
        edit_allowed = st.text_input(
            "Allowed origins",
            value=", ".join(widget.get("allowed_origins") or []),
            key=f"allowed-{widget['id']}",
        )
        edit_theme = st.text_area(
            "Theme config (JSON)",
            value=json.dumps(widget.get("theme_config") or {}, indent=2),
            key=f"theme-{widget['id']}",
        )
        if st.button("Save", key=f"save-{widget['id']}"):
            try:
                payload = {
                    "greeting": edit_greeting or None,
                    "allowed_origins": [o.strip() for o in edit_allowed.split(",") if o.strip()],
                    "theme_config": json.loads(edit_theme) if edit_theme else {},
                }
                patch_response = requests.patch(
                    f"{API_BASE_URL}/admin/widgets/{widget['id']}",
                    headers={**headers, "Content-Type": "application/json"},
                    json=payload,
                    timeout=10,
                )
                patch_response.raise_for_status()
                st.success("Widget updated")
                st.rerun()
            except json.JSONDecodeError:
                st.error("Theme config must be valid JSON")
            except requests.HTTPError:
                st.error("Failed to update widget")
