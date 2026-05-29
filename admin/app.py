import os
from typing import Any

import jwt
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9000")

st.set_page_config(page_title="Concierge Admin", layout="wide")


def _decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, options={"verify_signature": False})


def _login(username: str, password: str) -> str:
    response = requests.post(
        f"{API_BASE_URL}/auth/login",
        data={"username": username, "password": password},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _logout() -> None:
    for key in ["access_token", "role", "tenant_id", "email"]:
        st.session_state.pop(key, None)


def _login_page() -> None:
    st.title("Concierge Admin")
    with st.form("login"):
        st.subheader("Sign in")
        username = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        try:
            token = _login(username, password)
            claims = _decode_token(token)
            st.session_state["access_token"] = token
            st.session_state["role"] = claims.get("role")
            st.session_state["tenant_id"] = claims.get("tenant_id")
            st.session_state["email"] = claims.get("email")
            st.success("Logged in")
            st.rerun()
        except requests.HTTPError:
            st.error("Login failed")


if not st.session_state.get("access_token"):
    pg = st.navigation([st.Page(_login_page, title="Login", icon="🔐")])
else:
    role = st.session_state.get("role")
    email = st.session_state.get("email", "")

    st.sidebar.title("Concierge Admin")
    st.sidebar.caption(f"{email}")
    st.sidebar.caption(f"Role: **{role}**")
    if st.sidebar.button("Log out"):
        _logout()
        st.rerun()
    st.sidebar.divider()

    if role == "tenant_admin":
        pg = st.navigation({
            "Content": [
                st.Page("pages/1_CMS.py", title="CMS", icon="📄"),
                st.Page("pages/2_Widgets.py", title="Widgets", icon="🧩"),
                st.Page("pages/3_Guardrails.py", title="Guardrails", icon="🛡️"),
            ],
            "Operations": [
                st.Page("pages/4_Leads.py", title="Leads", icon="📋"),
                st.Page("pages/5_Snippet.py", title="Embed Snippet", icon="🔗"),
            ],
        })
    elif role == "tenant_manager":
        pg = st.navigation({
            "Platform": [
                st.Page("pages/6_Tenants.py", title="Tenants", icon="🏢"),
                st.Page("pages/7_Audit_Log.py", title="Audit Log", icon="📜"),
            ],
        })
    else:
        st.error(f"Role '{role}' is not permitted to use this UI.")
        st.stop()

pg.run()
