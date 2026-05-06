"""ChromaDB-backed vector store with local sentence-transformer embeddings.

Supports multiple named knowledge bases, each stored as a separate collection.
"""

import re


def make_collection_name(display_name: str) -> str:
    """Convert a human-readable KB name to a valid ChromaDB collection name.

    ChromaDB requires: 3-63 chars, alphanumeric/underscore/hyphen only,
    must start and end with alphanumeric.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", display_name.strip().lower()).strip("_")
    name = f"kb_{sanitized or 'default'}"
    return name[:63]


class _SentenceTransformerEF:
    """Embedding function for ChromaDB. Shares the model across all instances."""

    _model_cache: dict = {}  # class-level — model loaded only once per process

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        if model_name not in self.__class__._model_cache:
            from sentence_transformers import SentenceTransformer
            self.__class__._model_cache[model_name] = SentenceTransformer(model_name)
        self._model = self.__class__._model_cache[model_name]

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return self._model.encode(input, show_progress_bar=False).tolist()

    def name(self) -> str:
        return "sentence-transformer-ef"

    def embed_query(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return self._model.encode(input, show_progress_bar=False).tolist()


class VectorStore:
    def __init__(
        self,
        persist_dir: str = "./chroma_db",
        collection_name: str = "rag_documents",
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        import chromadb

        self._ef = _SentenceTransformerEF(embedding_model)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection_name = collection_name
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_documents(self, chunks: list[dict]) -> int:
        """Add chunks to this KB. Returns the number of new chunks added."""
        if not chunks:
            return 0

        existing_ids = set(self._collection.get(include=[])["ids"])
        texts, ids, metadatas = [], [], []

        for i, chunk in enumerate(chunks):
            source = chunk["metadata"].get("source", "unknown")
            chunk_idx = chunk["metadata"].get("chunk_index", i)
            uid = f"{source}_{chunk_idx}"
            if uid in existing_ids:
                continue
            texts.append(chunk["text"])
            ids.append(uid)
            metadatas.append({k: str(v) for k, v in chunk["metadata"].items()})

        if texts:
            self._collection.add(documents=texts, ids=ids, metadatas=metadatas)

        return len(texts)

    def clear(self) -> None:
        """Remove all documents from this KB's collection."""
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Return top-k most relevant chunks. Each result has text, source, distance, drive_url."""
        if self.count() == 0:
            return []

        results = self._collection.query(
            query_texts=[query],
            n_results=min(top_k, self.count()),
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        for text, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            hits.append(
                {
                    "text": text,
                    "source": meta.get("source", "unknown"),
                    "distance": dist,
                    "drive_url": meta.get("drive_url", ""),
                }
            )
        return hits

    def count(self) -> int:
        return self._collection.count()

    def list_sources(self) -> list[str]:
        """Return deduplicated list of source document names in this KB."""
        if self.count() == 0:
            return []
        data = self._collection.get(include=["metadatas"])
        seen: set[str] = set()
        for meta in data["metadatas"]:
            seen.add(meta.get("source", "unknown"))
        return sorted(seen)
