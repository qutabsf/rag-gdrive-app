# 📚 RAG Knowledge Base — Google Drive + Claude

A local AI-powered app that connects to your Google Drive, ingests documents into a searchable vector database, and lets you chat with that content using Anthropic's Claude — getting accurate, source-cited answers grounded strictly in your own documentation.

It supports **multiple named knowledge bases** with separate conversations, so you can organize different document sets (e.g. HR Policies, Product SOPs) and query each independently — just like having separate chats in Claude or ChatGPT.

---

## ✨ Features

- **Google Drive integration** — paste a folder or file link; the app fetches everything automatically
- **Supports multiple file types** — Google Docs, Sheets, Slides, PDFs, Word (.docx), plain text, Markdown
- **Multiple knowledge bases** — create and name separate KBs, each stored independently
- **Separate chat histories** — each KB has its own conversation, switch between them instantly
- **Clickable source links** — every answer shows which documents it used, with direct links back to Google Drive
- **Follow-up questions** — full multi-turn conversation, Claude remembers the whole session
- **Free local embeddings** — uses `sentence-transformers` (no API key or cost for embeddings)
- **Persistent storage** — ingested documents survive app restarts; no need to re-ingest
- **Streaming answers** — responses stream token-by-token, just like Claude.ai

---

## 🖥️ Screenshots

| Ingest Tab | Chat Tab |
|---|---|
| Name your KB, paste a Drive URL, click Fetch & Index | Select a KB, ask questions, get sourced answers |

---

## 🏗️ Architecture

```
Google Drive
     │
     ▼
gdrive_fetcher.py       ← OAuth 2.0 auth, file listing & downloading
     │
     ▼
document_processor.py   ← Text extraction (PDF, DOCX, plain text) + chunking
     │
     ▼
vector_store.py         ← ChromaDB + sentence-transformers embeddings (local)
     │
     ▼
rag_chain.py            ← Retrieves relevant chunks → streams answer via Claude
     │
     ▼
app.py                  ← Streamlit UI (Ingest tab + Chat tab)
```

---

## ⚙️ Setup

### 1. Prerequisites

- **Python 3.11+** — download from [python.org](https://www.python.org/downloads/) (check "Add to PATH" during install)
- **Anthropic API key** — get one free at [console.anthropic.com](https://console.anthropic.com)
- **Google Cloud project** — for Drive access (free, see below)

### 2. Clone & install

```bash
git clone https://github.com/qutabsf/rag-gdrive-app.git
cd rag-gdrive-app
pip install -r requirements.txt
```

### 3. Set your Anthropic API key

Copy `.env.example` to `.env` and fill in your key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Set up Google Drive access

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a new project
2. Enable the **Google Drive API** (APIs & Services → Library → search "Google Drive API" → Enable)
3. Create OAuth credentials: APIs & Services → Credentials → Create Credentials → **OAuth client ID** → Desktop app → Download JSON
4. Rename the downloaded file to `credentials.json` and place it in the project folder
5. Go to **APIs & Services → OAuth consent screen → Test users** and add your own Gmail address

### 5. Run

**Windows** — double-click `run.bat`

**Mac / Linux:**
```bash
streamlit run app.py
```

The app opens at **http://localhost:8501**

---

## 🚀 How to use

### Creating a Knowledge Base
1. Go to the **📥 Ingest** tab
2. Enter a name for your KB (e.g. "HR Policies")
3. Paste a Google Drive folder or file URL
4. Click **Fetch & Index** — the app downloads, chunks, and indexes everything

### Chatting with your documents
1. Go to the **💬 Chat** tab
2. Select a knowledge base from the dropdown
3. Ask any question — Claude answers using only your documents
4. Click the **📎 Sources used** expander to see which files were referenced, with clickable links back to Google Drive
5. Ask follow-up questions freely — the full conversation context is remembered

### Managing Knowledge Bases
- Add as many KBs as you like — each is stored separately
- Delete a KB from the Ingest tab using the 🗑️ Delete button
- The sidebar shows all your KBs and their chunk counts

---

## 📦 Tech Stack

| Component | Library |
|---|---|
| UI | [Streamlit](https://streamlit.io) |
| LLM | [Anthropic Claude](https://anthropic.com) (`claude-opus-4-7` default) |
| Embeddings | [sentence-transformers](https://www.sbert.net/) (`all-MiniLM-L6-v2`) |
| Vector DB | [ChromaDB](https://www.trychroma.com/) (local, persistent) |
| Google Drive | `google-api-python-client` + `google-auth-oauthlib` |
| PDF parsing | [pypdf](https://pypdf.readthedocs.io/) |
| DOCX parsing | [python-docx](https://python-docx.readthedocs.io/) |

---

## 🔒 Security & Privacy

- Your documents are stored **locally** on your machine inside the `chroma_db/` folder
- The only data sent externally is your questions + relevant document chunks, sent to Anthropic's API for answer generation
- `credentials.json`, `token.json`, and `.env` are excluded from git via `.gitignore` — they will never be committed

---

## 📄 License

MIT License — free to use, modify, and distribute.
