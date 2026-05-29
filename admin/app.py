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
    payload = response.json()
    return payload["access_token"]


def _logout() -> None:
    for key in ["access_token", "role", "tenant_id", "email"]:
        st.session_state.pop(key, None)


st.sidebar.title("Concierge Admin")

if st.session_state.get("access_token"):
    _role = st.session_state.get("role")
    if _role == "tenant_admin":
        st.sidebar.page_link("pages/1_CMS.py", label="CMS")
        st.sidebar.page_link("pages/2_Widgets.py", label="Widgets")
        st.sidebar.page_link("pages/3_Guardrails.py", label="Guardrails")
        st.sidebar.page_link("pages/4_Leads.py", label="Leads")
        st.sidebar.page_link("pages/5_Snippet.py", label="Snippet")
    elif _role == "tenant_manager":
        st.sidebar.page_link("pages/6_Tenants.py", label="Tenants")
        st.sidebar.page_link("pages/7_Audit_Log.py", label="Audit Log")

    if st.sidebar.button("Log out"):
        _logout()
        st.rerun()

st.title("Concierge Admin")

if not st.session_state.get("access_token"):
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
else:
    role = st.session_state.get("role")
    st.success(f"Signed in as {st.session_state.get('email')} ({role})")
    if role not in {"tenant_admin", "tenant_manager"}:
        st.warning("This UI requires tenant_admin or tenant_manager role.")
