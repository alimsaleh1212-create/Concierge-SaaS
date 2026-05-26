import os

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.title("Leads")

token = st.session_state.get("access_token")
role = st.session_state.get("role")
if not token:
    st.warning("Please log in from the main page.")
    st.stop()
if role != "tenant_admin":
    st.error("Leads require tenant_admin role.")
    st.stop()

headers = {"Authorization": f"Bearer {token}"}

status = st.selectbox("Status", ["new", "contacted", "closed"], index=0)
response = requests.get(
    f"{API_BASE_URL}/admin/leads",
    headers=headers,
    params={"status": status},
    timeout=10,
)
response.raise_for_status()
leads = response.json().get("leads", [])

if not leads:
    st.info("No leads for this status.")

for lead in leads:
    with st.expander(f"{lead.get('name', 'Lead')} ({lead.get('id')})"):
        st.write(lead)
        next_status = st.selectbox(
            "Update status",
            ["new", "contacted", "closed"],
            index=["new", "contacted", "closed"].index(lead.get("status", "new")),
            key=f"status-{lead['id']}",
        )
        if st.button("Update", key=f"update-{lead['id']}"):
            patch_response = requests.patch(
                f"{API_BASE_URL}/admin/leads/{lead['id']}",
                headers={**headers, "Content-Type": "application/json"},
                json={"status": next_status},
                timeout=10,
            )
            if patch_response.ok:
                st.success("Lead updated")
                st.rerun()
            else:
                st.error("Failed to update lead")
