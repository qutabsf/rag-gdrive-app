"""RAG Knowledge Base — Google Drive + Claude — multi-KB edition.

Run with:  streamlit run app.py
"""

import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="RAG Knowledge Base",
    page_icon="📚",
    layout="wide",
)

# ── Imports ───────────────────────────────────────────────────────────────────
from gdrive_fetcher import (  # noqa: E402
    authenticate,
    build_service,
    fetch_file_bytes,
    get_file_metadata,
    list_folder_files,
    load_credentials,
    parse_drive_url,
)
from document_processor import chunk_text, extract_text  # noqa: E402
from vector_store import VectorStore, make_collection_name  # noqa: E402
from rag_chain import get_no_context_response, stream_rag_response  # noqa: E402

PERSIST_DIR = str(Path(__file__).parent / "chroma_db")
CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
KB_REGISTRY_PATH = str(Path(__file__).parent / "kb_registry.json")

MODELS = {
    "claude-opus-4-7 (most capable)": "claude-opus-4-7",
    "claude-haiku-4-5 (fastest / cheapest)": "claude-haiku-4-5",
    "claude-sonnet-4-6 (balanced)": "claude-sonnet-4-6",
}


# ── KB Registry (persisted to disk) ──────────────────────────────────────────

def load_kb_registry() -> dict:
    """Load {display_name: collection_name} mapping from disk."""
    try:
        with open(KB_REGISTRY_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_kb_registry(registry: dict) -> None:
    with open(KB_REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)


# ── Cached VectorStore loader ─────────────────────────────────────────────────
# One cached instance per collection — the embedding model is shared internally.

@st.cache_resource(show_spinner="Loading knowledge base…")
def _load_vs(persist_dir: str, collection_name: str) -> VectorStore:
    return VectorStore(persist_dir=persist_dir, collection_name=collection_name)


def get_vs(kb_name: str) -> VectorStore:
    """Return the VectorStore for a named KB."""
    collection_name = st.session_state.kb_registry[kb_name]
    return _load_vs(PERSIST_DIR, collection_name)


# ── Session-state helpers ─────────────────────────────────────────────────────

def init_session():
    defaults = {
        "authenticated": False,
        "creds": None,
        "kb_registry": load_kb_registry(),   # {display_name: collection_name}
        "chat_histories": {},                 # {kb_name: [{"role", "content"}]}
        "processing": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.title("⚙️ Settings")

        # --- API key ---
        api_key = st.text_input(
            "Anthropic API Key",
            value=os.getenv("ANTHROPIC_API_KEY", ""),
            type="password",
            help="Get your key at https://console.anthropic.com",
        )

        # --- Model ---
        model_label = st.selectbox("Claude Model", list(MODELS.keys()), index=0)
        model = MODELS[model_label]

        st.divider()

        # --- Google Drive auth ---
        st.subheader("Google Drive")

        if st.session_state.authenticated:
            st.success("✅ Connected to Google Drive")
            if st.button("Disconnect", use_container_width=True):
                token_path = Path(__file__).parent / "token.json"
                token_path.unlink(missing_ok=True)
                st.session_state.authenticated = False
                st.session_state.creds = None
                st.rerun()
        else:
            st.info(
                "You need a `credentials.json` file from Google Cloud Console.\n"
                "See **Setup Guide** below for instructions."
            )
            credentials_path = st.text_input(
                "Path to credentials.json",
                value=CREDENTIALS_PATH,
                help="Desktop-app OAuth 2.0 credentials downloaded from GCP.",
            )
            if st.button("Connect Google Drive", use_container_width=True, type="primary"):
                try:
                    creds = load_credentials(credentials_path)
                    if creds is None:
                        creds = authenticate(credentials_path)
                    st.session_state.creds = creds
                    st.session_state.authenticated = True
                    st.rerun()
                except FileNotFoundError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Authentication failed: {exc}")

        st.divider()

        # --- All knowledge bases ---
        st.subheader("Knowledge Bases")
        registry = st.session_state.kb_registry

        if not registry:
            st.caption("No knowledge bases yet.")
        else:
            for kb_name, coll_name in list(registry.items()):
                try:
                    vs = _load_vs(PERSIST_DIR, coll_name)
                    count = vs.count()
                    st.markdown(f"**{kb_name}**  \n{count:,} chunks")
                except Exception:
                    st.markdown(f"**{kb_name}**  \n—")

        with st.expander("📖 Setup Guide"):
            st.markdown(
                """
**1. Create a Google Cloud project**
- Go to [console.cloud.google.com](https://console.cloud.google.com)
- Create a new project

**2. Enable Drive API**
- APIs & Services → Library → *Google Drive API* → Enable

**3. Create OAuth credentials**
- APIs & Services → Credentials → *Create Credentials* → OAuth client ID
- Application type: **Desktop app**
- Download the JSON and save as `credentials.json` in this folder

**4. Set Anthropic API key**
- Get key at [console.anthropic.com](https://console.anthropic.com)
- Paste it in the sidebar or set `ANTHROPIC_API_KEY` in a `.env` file
"""
            )

    return api_key, model


# ── Main: Ingest tab ──────────────────────────────────────────────────────────

def render_ingest_tab():
    st.header("📥 Ingest Documentation")

    # ── Two input fields side by side ────────────────────────────────────────
    col1, col2 = st.columns([1, 2])

    kb_name_input = col1.text_input(
        "Name of your KB",
        placeholder="e.g. HR Policies, Product Docs, SOPs…",
        help="Give this knowledge base a name. You can have as many as you like.",
    )
    drive_url_input = col2.text_input(
        "Google Drive URL",
        placeholder="https://drive.google.com/drive/folders/… or a file/doc link",
        help="Paste a shared Google Drive folder or file URL.",
    )

    # ── Validation hints ─────────────────────────────────────────────────────
    if not st.session_state.authenticated:
        st.warning("⚠️ Connect Google Drive in the sidebar first.")
    elif not kb_name_input.strip():
        st.info("👆 Enter a name for this knowledge base.")
    elif not drive_url_input.strip():
        st.info("👆 Paste a Google Drive URL.")

    can_fetch = (
        st.session_state.authenticated
        and kb_name_input.strip()
        and drive_url_input.strip()
    )
    fetch_clicked = st.button("Fetch & Index", type="primary", disabled=not can_fetch)

    # ── Existing KBs ─────────────────────────────────────────────────────────
    registry = st.session_state.kb_registry
    if registry:
        st.divider()
        st.subheader("Existing Knowledge Bases")
        for kb_name, coll_name in list(registry.items()):
            try:
                vs = _load_vs(PERSIST_DIR, coll_name)
                count = vs.count()
                sources = vs.list_sources()
                col_info, col_del = st.columns([5, 1])
                with col_info:
                    with st.expander(f"📚 **{kb_name}** — {count:,} chunks, {len(sources)} file(s)"):
                        for s in sources:
                            st.caption(f"• {s}")
                with col_del:
                    # Align button vertically with the expander header
                    st.write("")
                    if st.button("🗑️ Delete", key=f"del_{coll_name}",
                                 help=f"Permanently delete '{kb_name}'"):
                        vs.clear()
                        del st.session_state.kb_registry[kb_name]
                        st.session_state.chat_histories.pop(kb_name, None)
                        save_kb_registry(st.session_state.kb_registry)
                        st.rerun()
            except Exception:
                pass

    # ── Ingestion logic ───────────────────────────────────────────────────────
    if fetch_clicked and can_fetch:
        kb_name = kb_name_input.strip()
        drive_url = drive_url_input.strip()

        resource_id, resource_type = parse_drive_url(drive_url)
        if not resource_id:
            st.error("Could not parse a Google Drive/Docs ID from that URL. Check the link and try again.")
            return

        # Register the KB (create collection name if new)
        if kb_name not in st.session_state.kb_registry:
            st.session_state.kb_registry[kb_name] = make_collection_name(kb_name)
            save_kb_registry(st.session_state.kb_registry)

        collection_name = st.session_state.kb_registry[kb_name]
        vs = _load_vs(PERSIST_DIR, collection_name)
        service = build_service(st.session_state.creds)

        with st.spinner("Listing files…"):
            if resource_type == "folder":
                files = list_folder_files(service, resource_id)
                if not files:
                    st.warning("No supported files found in that folder.")
                    return
            else:
                meta = get_file_metadata(service, resource_id)
                files = [meta]

        st.info(f"Found **{len(files)} file(s)** to process into **{kb_name}**.")
        progress = st.progress(0, text="Starting…")
        log = st.empty()
        total_chunks = 0

        for i, file in enumerate(files):
            file_name = file["name"]
            mime_type = file["mimeType"]
            log.write(f"Processing: **{file_name}**")

            try:
                raw_bytes, effective_mime = fetch_file_bytes(service, file["id"], mime_type)
                text = extract_text(raw_bytes, effective_mime, file_name)

                if not text.strip():
                    log.warning(f"No text extracted from {file_name} — skipping.")
                    continue

                drive_file_url = f"https://drive.google.com/open?id={file['id']}"
                chunks = chunk_text(
                    text,
                    metadata={
                        "source": file_name,
                        "drive_id": file["id"],
                        "drive_url": drive_file_url,
                    },
                )
                added = vs.add_documents(chunks)
                total_chunks += added
                log.write(f"✅ **{file_name}** → {added} chunk(s) added.")

            except Exception as exc:
                log.error(f"Failed to process {file_name}: {exc}")

            progress.progress((i + 1) / len(files), text=f"{i + 1}/{len(files)} files")

        progress.empty()
        st.success(
            f"Done! Indexed **{total_chunks} new chunks** from {len(files)} file(s) "
            f"into **{kb_name}**. Switch to the 💬 Chat tab to start asking questions."
        )
        st.rerun()


# ── Main: Chat tab ────────────────────────────────────────────────────────────

def render_chat_tab(api_key: str, model: str):
    st.header("💬 Ask Your Documentation")

    registry = st.session_state.kb_registry
    if not registry:
        st.info("No knowledge bases yet. Go to the **📥 Ingest** tab to create your first one.")
        return

    if not api_key:
        st.warning("Enter your Anthropic API key in the sidebar to use the chat.")
        return

    # ── KB selector ───────────────────────────────────────────────────────────
    kb_names = list(registry.keys())
    selected_kb = st.selectbox(
        "Select Knowledge Base",
        kb_names,
        key="active_kb_selector",
        help="Each knowledge base has its own separate conversation history.",
    )

    # Ensure this KB has a chat history slot
    if selected_kb not in st.session_state.chat_histories:
        st.session_state.chat_histories[selected_kb] = []

    vs = get_vs(selected_kb)

    if vs.count() == 0:
        st.warning(
            f"**{selected_kb}** has no documents indexed yet. "
            "Go to the **📥 Ingest** tab and add a Google Drive URL for this KB."
        )
        return

    sources = vs.list_sources()
    st.caption(f"Chatting with **{selected_kb}** · {vs.count():,} chunks · {len(sources)} file(s)")
    st.divider()

    # ── Render this KB's conversation history ─────────────────────────────────
    history = st.session_state.chat_histories[selected_kb]
    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Chat input ────────────────────────────────────────────────────────────
    if prompt := st.chat_input(f"Ask a question about {selected_kb}…"):
        with st.chat_message("user"):
            st.markdown(prompt)
        history.append({"role": "user", "content": prompt})

        chunks = vs.search(prompt, top_k=5)

        with st.chat_message("assistant"):
            if not chunks:
                answer = get_no_context_response()
                st.markdown(answer)
            else:
                with st.expander("📎 Sources used", expanded=False):
                    seen: set[str] = set()
                    for c in chunks:
                        if c["source"] not in seen:
                            seen.add(c["source"])
                            relevance = round((1 - c["distance"]) * 100, 1)
                            url = c.get("drive_url", "")
                            if url:
                                st.caption(f"• [{c['source']}]({url})  (relevance: {relevance}%)")
                            else:
                                st.caption(f"• {c['source']}  (relevance: {relevance}%)")

                try:
                    answer = st.write_stream(
                        stream_rag_response(
                            prompt,
                            chunks,
                            api_key,
                            model,
                            chat_history=history,
                        )
                    )
                except Exception as exc:
                    answer = f"Error generating response: {exc}"
                    st.error(answer)

        history.append({"role": "assistant", "content": answer})
        st.session_state.chat_histories[selected_kb] = history

    # ── Clear this KB's chat ──────────────────────────────────────────────────
    if history:
        if st.button("Clear chat history", key=f"clear_{selected_kb}"):
            st.session_state.chat_histories[selected_kb] = []
            st.rerun()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    init_session()

    # Restore Google credentials from saved token
    if not st.session_state.authenticated:
        creds = load_credentials(CREDENTIALS_PATH)
        if creds:
            st.session_state.creds = creds
            st.session_state.authenticated = True

    # ── Migrate legacy single-KB data (one-time, on first run with new code) ──
    if not st.session_state.kb_registry:
        try:
            import chromadb as _chroma
            _client = _chroma.PersistentClient(path=PERSIST_DIR)
            _existing = [c.name for c in _client.list_collections()]
            if "rag_documents" in _existing:
                _legacy_vs = _load_vs(PERSIST_DIR, "rag_documents")
                if _legacy_vs.count() > 0:
                    st.session_state.kb_registry["My Knowledge Base"] = "rag_documents"
                    save_kb_registry(st.session_state.kb_registry)
        except Exception:
            pass

    api_key, model = render_sidebar()

    ingest_tab, chat_tab = st.tabs(["📥 Ingest", "💬 Chat"])

    with ingest_tab:
        render_ingest_tab()

    with chat_tab:
        render_chat_tab(api_key, model)


if __name__ == "__main__":
    main()
