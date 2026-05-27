import json
import os

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.title("CMS")

token = st.session_state.get("access_token")
role = st.session_state.get("role")
if not token:
    st.warning("Please log in from the main page.")
    st.stop()
if role != "tenant_admin":
    st.error("CMS requires tenant_admin role.")
    st.stop()

headers = {"Authorization": f"Bearer {token}"}

if st.button("Refresh"):
    st.rerun()

response = requests.get(f"{API_BASE_URL}/admin/cms", headers=headers, timeout=10)
response.raise_for_status()
items = response.json().get("items", [])

st.subheader("Create CMS Item")
with st.form("create_cms"):
    title = st.text_input("Title")
    body = st.text_area("Body")
    content_type = st.selectbox("Content type", ["faq", "page", "product"])
    metadata_text = st.text_area("Metadata (JSON)", value="{}")
    submitted = st.form_submit_button("Create")

if submitted:
    try:
        metadata = json.loads(metadata_text) if metadata_text else {}
        payload = {
            "title": title,
            "body": body,
            "content_type": content_type,
            "metadata": metadata,
        }
        create_response = requests.post(
            f"{API_BASE_URL}/admin/cms",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        create_response.raise_for_status()
        st.success("CMS item created")
        st.rerun()
    except json.JSONDecodeError:
        st.error("Metadata must be valid JSON")
    except requests.HTTPError:
        st.error("Failed to create CMS item")

st.subheader("Existing Items")
for item in items:
    with st.expander(f"{item.get('title')} ({item.get('id')})"):
        edit_title = st.text_input("Title", value=item.get("title"), key=f"title-{item['id']}")
        edit_body = st.text_area("Body", value=item.get("body", ""), key=f"body-{item['id']}")
        edit_type = st.selectbox(
            "Content type",
            ["faq", "page", "product"],
            index=["faq", "page", "product"].index(item.get("content_type", "faq")),
            key=f"type-{item['id']}",
        )
        edit_meta = st.text_area(
            "Metadata (JSON)",
            value=json.dumps(item.get("metadata") or {}, indent=2),
            key=f"meta-{item['id']}",
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Save", key=f"save-{item['id']}"):
                try:
                    payload = {
                        "title": edit_title,
                        "body": edit_body,
                        "content_type": edit_type,
                        "metadata": json.loads(edit_meta) if edit_meta else {},
                    }
                    patch_response = requests.patch(
                        f"{API_BASE_URL}/admin/cms/{item['id']}",
                        headers={**headers, "Content-Type": "application/json"},
                        json=payload,
                        timeout=10,
                    )
                    patch_response.raise_for_status()
                    st.success("Updated")
                    st.rerun()
                except json.JSONDecodeError:
                    st.error("Metadata must be valid JSON")
                except requests.HTTPError:
                    st.error("Failed to update item")
        with col2:
            confirm = st.checkbox("Confirm delete", key=f"del-confirm-{item['id']}")
            if st.button("Delete", key=f"delete-{item['id']}"):
                if not confirm:
                    st.warning("Please confirm delete first")
                else:
                    delete_response = requests.delete(
                        f"{API_BASE_URL}/admin/cms/{item['id']}",
                        headers=headers,
                        timeout=10,
                    )
                    if delete_response.ok:
                        st.success("Deleted")
                        st.rerun()
                    else:
                        st.error("Failed to delete item")
