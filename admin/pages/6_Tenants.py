import os

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.title("Tenant Management")

token = st.session_state.get("access_token")
role = st.session_state.get("role")
if not token:
    st.warning("Please log in from the main page.")
    st.stop()
if role != "tenant_manager":
    st.error("This page requires the tenant_manager role.")
    st.stop()

headers = {"Authorization": f"Bearer {token}"}

if st.button("Refresh"):
    st.rerun()

response = requests.get(f"{API_BASE_URL}/platform/tenants", headers=headers, timeout=10)
response.raise_for_status()
tenants = response.json().get("tenants", [])

# --- Provision new tenant ---
st.subheader("Provision New Tenant")
with st.form("provision"):
    name = st.text_input("Tenant name")
    slug = st.text_input("Slug (unique, URL-safe)")
    origins = st.text_input("Allowed origins (comma separated)")
    submitted = st.form_submit_button("Provision")

if submitted:
    payload = {
        "name": name,
        "slug": slug,
        "allowed_origins": [o.strip() for o in origins.split(",") if o.strip()],
    }
    try:
        r = requests.post(
            f"{API_BASE_URL}/platform/tenants",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        r.raise_for_status()
        st.success(f"Tenant provisioned: {r.json().get('slug')} ({r.json().get('id')})")
        st.rerun()
    except requests.HTTPError as exc:
        st.error(f"Failed to provision tenant: {exc.response.text if exc.response else exc}")

# --- Existing tenants ---
st.subheader("Existing Tenants")

if not tenants:
    st.info("No tenants found.")
else:
    for tenant in tenants:
        tid = tenant["id"]
        label = f"{'🟢' if tenant.get('is_active') else '🔴'} {tenant['name']} — {tenant['slug']}"
        with st.expander(label):
            col1, col2 = st.columns(2)
            col1.metric("Messages (7d)", tenant.get("message_count_7d", 0))
            col2.metric("Cost (7d USD)", f"${tenant.get('cost_7d_usd', 0.0):.4f}")

            st.write(f"**ID**: `{tid}`")
            st.write(f"**Active**: {tenant.get('is_active')}")

            # Invite tenant_admin
            st.markdown("**Invite tenant admin**")
            invite_email = st.text_input("Admin email", key=f"invite-{tid}")
            if st.button("Send invite", key=f"invite-btn-{tid}"):
                if not invite_email:
                    st.warning("Enter an email address first.")
                else:
                    try:
                        r = requests.post(
                            f"{API_BASE_URL}/platform/tenants/{tid}/invite",
                            headers={**headers, "Content-Type": "application/json"},
                            json={"email": invite_email},
                            timeout=10,
                        )
                        r.raise_for_status()
                        st.success(f"Invited {invite_email}")
                    except requests.HTTPError as exc:
                        st.error(f"Invite failed: {exc.response.text if exc.response else exc}")

            st.markdown("---")

            # Suspend / Erase — only show if active
            col_suspend, col_erase = st.columns(2)

            with col_suspend:
                if tenant.get("is_active"):
                    confirm_suspend = st.checkbox("Confirm suspend", key=f"confirm-suspend-{tid}")
                    if st.button("Suspend", key=f"suspend-{tid}"):
                        if not confirm_suspend:
                            st.warning("Check the confirmation box first.")
                        else:
                            try:
                                r = requests.patch(
                                    f"{API_BASE_URL}/platform/tenants/{tid}/suspend",
                                    headers={**headers, "Content-Type": "application/json"},
                                    json={"reason": "Suspended via admin UI"},
                                    timeout=10,
                                )
                                r.raise_for_status()
                                st.success("Tenant suspended")
                                st.rerun()
                            except requests.HTTPError as exc:
                                st.error(f"Suspend failed: {exc.response.text if exc.response else exc}")
                else:
                    st.info("Already suspended")

            with col_erase:
                st.markdown(":red[**Right-to-erasure — irreversible**]")
                confirm_erase = st.checkbox("I understand this is permanent", key=f"confirm-erase-{tid}")
                if st.button("Erase tenant", key=f"erase-{tid}"):
                    if not confirm_erase:
                        st.warning("Check the confirmation box first.")
                    else:
                        try:
                            r = requests.delete(
                                f"{API_BASE_URL}/platform/tenants/{tid}",
                                headers=headers,
                                timeout=30,
                            )
                            r.raise_for_status()
                            st.success("Tenant erased from all stores")
                            st.rerun()
                        except requests.HTTPError as exc:
                            st.error(f"Erase failed: {exc.response.text if exc.response else exc}")
