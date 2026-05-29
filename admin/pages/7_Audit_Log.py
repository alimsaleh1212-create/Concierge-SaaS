import os

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.title("Audit Log")

token = st.session_state.get("access_token")
role = st.session_state.get("role")
if not token:
    st.warning("Please log in from the main page.")
    st.stop()
if role != "tenant_manager":
    st.error("This page requires the tenant_manager role.")
    st.stop()

headers = {"Authorization": f"Bearer {token}"}

col1, col2, col3 = st.columns(3)
tenant_filter = col1.text_input("Filter by tenant ID (optional)")
limit = col2.number_input("Limit", min_value=10, max_value=1000, value=100, step=10)
offset = col3.number_input("Offset", min_value=0, value=0, step=100)

params: dict = {"limit": int(limit), "offset": int(offset)}
if tenant_filter.strip():
    params["tenant_id"] = tenant_filter.strip()

if st.button("Refresh"):
    st.rerun()

try:
    response = requests.get(
        f"{API_BASE_URL}/platform/audit-log",
        headers=headers,
        params=params,
        timeout=10,
    )
    response.raise_for_status()
    entries = response.json().get("entries", [])
except requests.HTTPError as exc:
    st.error(f"Failed to load audit log: {exc.response.text if exc.response else exc}")
    st.stop()

st.caption(f"{len(entries)} entries (newest first)")

if not entries:
    st.info("No audit log entries found.")
else:
    for entry in entries:
        tid_label = entry["tenant_id"] or "platform"
        with st.expander(f"{entry['created_at'][:19]}  ·  {entry['action']}  ·  tenant: {tid_label}"):
            st.write(f"**Actor**: `{entry['actor_id']}` ({entry['actor_role']})")
            st.write(f"**Action**: `{entry['action']}`")
            st.write(f"**Tenant**: `{entry['tenant_id'] or '—'}`")
            if entry.get("metadata"):
                st.json(entry["metadata"])
