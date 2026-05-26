import os

import requests
import streamlit as st
import streamlit.components.v1 as components

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.title("Embed Snippet")

token = st.session_state.get("access_token")
role = st.session_state.get("role")
if not token:
    st.warning("Please log in from the main page.")
    st.stop()
if role != "tenant_admin":
    st.error("Embed snippet requires tenant_admin role.")
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

snippet_response = requests.get(
    f"{API_BASE_URL}/admin/widgets/{selected_widget['id']}/snippet",
    headers=headers,
    timeout=10,
)
snippet_response.raise_for_status()

snippet = snippet_response.json().get("snippet", "")

st.subheader("HTML Snippet")
st.code(snippet, language="html")

components.html(
    f"""
    <button id='copy-snippet' style='padding:8px 12px;border-radius:8px;border:none;background:#f25c54;color:#0b0d12;font-weight:600;'>Copy to clipboard</button>
    <script>
      const btn = document.getElementById('copy-snippet');
      btn.addEventListener('click', async () => {{
        await navigator.clipboard.writeText({snippet!r});
        btn.textContent = 'Copied!';
        setTimeout(() => {{ btn.textContent = 'Copy to clipboard'; }}, 1500);
      }});
    </script>
    """,
    height=60,
)

st.subheader("Preview")
components.html(
    f"""
    <iframe srcdoc='{snippet.replace("'", "&apos;")}' style='width:100%;height:420px;border:1px solid #eee;'></iframe>
    """,
    height=440,
)
