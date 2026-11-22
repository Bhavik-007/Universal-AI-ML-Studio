# pages/9_MCP_Model.py
import streamlit as st

from auth.login_manager import login_manager
from auth.auth_guard import protect_page




st.set_page_config(page_title="MCP Model Deployment", layout="wide")
login_manager()
protect_page()

from auth.ui_guard import apply_sidebar_visibility

import os
import subprocess
import tempfile
import requests
import plotly.express as px

# =========================================================
# --- LOGIN + SIDEBAR GUARD ---
# =========================================================
apply_sidebar_visibility()


# =========================================================
# --- Streamlit Config ---
# =========================================================
st.cache_resource.show_spinner = False  # Disable spinner globally

# =========================================================
# --- Sidebar ---
# =========================================================
with st.sidebar:
    st.markdown("<h2>🗂️ MCP Model Deployment</h2>", unsafe_allow_html=True)
    st.markdown("Visualize and explore your **Streamlit app folder structure** from a local path or a GitHub repo.")

    st.markdown("---")
    st.markdown(f"👤 Logged in as **{st.session_state.get('username', 'User')}**")
# --- Page Header ---
# =========================================================
st.title("🗂️ App Components Structure")
st.markdown("Choose a **local folder** or a **GitHub repo URL** to explore its structure:")

# =========================================================
# --- GitHub Clone Helper ---
# =========================================================
def clone_github_repo(github_url):
    tmp_dir = tempfile.mkdtemp()
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", github_url, tmp_dir],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return tmp_dir, None
    except subprocess.CalledProcessError as e:
        return None, f"❌ Failed to clone repo: {e.stderr.decode()}"

# =========================================================
# --- GitHub API Fallback ---
# =========================================================
def fetch_github_tree(github_url):
    try:
        parts = github_url.strip("/").split("/")
        user, repo = parts[-2], parts[-1].replace(".git", "")
        api_url = f"https://api.github.com/repos/{user}/{repo}/git/trees/main?recursive=1"
        r = requests.get(api_url)
        if r.status_code != 200:
            return None, f"❌ GitHub API error: {r.status_code}"
        data = r.json()
        files = [item["path"] for item in data.get("tree", []) if item["type"] == "blob"]
        return files, None
    except Exception as e:
        return None, f"❌ Error fetching GitHub tree: {e}"

# =========================================================
# --- Static Tree Builder ---
# =========================================================
def build_tree(folder_path, prefix=""):
    tree_str = ""
    items = sorted(os.listdir(folder_path))
    for i, item in enumerate(items):
        path = os.path.join(folder_path, item)
        connector = "└── " if i == len(items) - 1 else "├── "
        tree_str += prefix + connector + item + "\n"
        if os.path.isdir(path):
            extension = "    " if i == len(items) - 1 else "│   "
            tree_str += build_tree(path, prefix + extension)
    return tree_str

# =========================================================
# --- Collapsible Tree Builder ---
# =========================================================
def render_tree(folder_path):
    items = sorted(os.listdir(folder_path))
    for item in items:
        path = os.path.join(folder_path, item)
        if os.path.isdir(path):
            with st.expander(f"📂 {item}", expanded=False):
                render_tree(path)
        else:
            st.markdown(f"- 📄 `{item}`")

# =========================================================
# --- Build Hierarchy with File Sizes ---
# =========================================================
def build_hierarchy(folder_path):
    paths, sizes = [], []
    for root, _, files in os.walk(folder_path):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, folder_path)
            parts = rel_path.split(os.sep)
            paths.append(parts)
            sizes.append(os.path.getsize(full_path))
    return paths, sizes

# =========================================================
# --- Treemap Visualization ---
# =========================================================
def plot_treemap(folder_path):
    paths, sizes = build_hierarchy(folder_path)
    if not paths:
        return None

    names, parents, values = [], [], []
    node_map = {}

    for parts, size in zip(paths, sizes):
        for i in range(len(parts)):
            node = "/".join(parts[:i + 1])
            parent = "/".join(parts[:i]) if i > 0 else ""
            if node not in node_map:
                names.append(node)
                parents.append(parent)
                values.append(0)
                node_map[node] = len(names) - 1
            if i == len(parts) - 1:
                values[node_map[node]] += size

    labels = [n.split("/")[-1] if n else folder_path for n in names]

    fig = px.treemap(
        names=labels,
        parents=parents,
        values=values,
        title="📂 Folder Structure (Treemap, file size weighted)"
    )
    fig.update_traces(
        textinfo="label+value",
        hovertemplate="<b>%{label}</b><br>Size: %{value} bytes"
    )
    return fig

# =========================================================
# --- Main UI ---
# =========================================================
option = st.radio("📌 Select Input Type", ["Local Folder Path", "GitHub Repo URL"], index=0)

if option == "Local Folder Path":
    folder_path = st.text_input("📁 Enter local folder path:")
    if st.button("Show Structure"):
        if folder_path.strip() and os.path.isdir(folder_path):
            st.subheader("📋 Static Folder Structure (copy-paste friendly)")
            structure = build_tree(folder_path)
            st.code(structure, language="text")

            st.subheader("🪄 Interactive Collapsible Tree View")
            render_tree(folder_path)

            st.subheader("🌐 Treemap (File size weighted)")
            fig = plot_treemap(folder_path)
            if fig:
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("No files found to generate treemap.")
        else:
            st.warning("⚠️ Please enter a valid folder path.")

elif option == "GitHub Repo URL":
    github_url = st.text_input("🌐 Enter GitHub repo URL:")
    if st.button("Show Structure (GitHub)"):
        if github_url.strip():
            tmp_dir, err = clone_github_repo(github_url)
            if tmp_dir:
                st.success(f"✅ Repo cloned successfully from {github_url}")
                structure = build_tree(tmp_dir)
                st.subheader("📋 Static Folder Structure (copy-paste friendly)")
                st.code(structure, language="text")

                st.subheader("🪄 Interactive Collapsible Tree View")
                render_tree(tmp_dir)

                st.subheader("🌐 Treemap (File size weighted)")
                fig = plot_treemap(tmp_dir)
                if fig:
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.info("No files found to generate treemap.")
            else:
                st.error(err or "Unknown error cloning repo")
        else:
            st.warning("⚠️ Please enter a valid GitHub repo URL.")
