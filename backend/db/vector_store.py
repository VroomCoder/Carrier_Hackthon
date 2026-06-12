import os

# Must be set before huggingface_hub / chromadb import
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from agent_trace import log_search


class VectorStore:
    def __init__(self, persist_path: str):
        self.client = chromadb.PersistentClient(path=persist_path)
        self.ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self.okr_embeddings = self.client.get_or_create_collection(
            name="okr_embeddings",
            embedding_function=self.ef,
        )
        self.milestone_embeddings = self.client.get_or_create_collection(
            name="milestone_embeddings",
            embedding_function=self.ef,
        )
        self.policy_chunks = self.client.get_or_create_collection(
            name="policy_chunks",
            embedding_function=self.ef,
        )
        self.feedback_embeddings = self.client.get_or_create_collection(
            name="feedback_embeddings",
            embedding_function=self.ef,
        )

    # ── OKR SEMANTIC SEARCH ──────────────────────────────────────────

    def sync_okr(self, okr: dict) -> None:
        doc_text = f"{okr['title']}: {okr['description']}"
        self.okr_embeddings.upsert(
            ids=[okr["okr_id"]],
            documents=[doc_text],
            metadatas=[
                {
                    "okr_id": okr["okr_id"],
                    "title": okr["title"],
                    "category": okr["category"],
                    "status": okr.get("status", "active"),
                }
            ],
        )

    def remove_okr(self, okr_id: str) -> None:
        try:
            self.okr_embeddings.delete(ids=[okr_id])
        except Exception:
            pass

    def search_okrs(
        self,
        query: str,
        n_results: int = 3,
        status_filter: str = "active",
        category_boost: list[str] | None = None,
    ) -> list[dict]:
        try:
            count = self.okr_embeddings.count()
            if count == 0:
                return []
            results = self.okr_embeddings.query(
                query_texts=[query],
                n_results=min(n_results * 2, count),
            )
            if not results or not results.get("metadatas") or not results["metadatas"][0]:
                return []
            metas = results["metadatas"][0]
            filtered = [m for m in metas if m.get("status") == status_filter]
            if category_boost:
                boosted = [m for m in filtered if m.get("category") in category_boost]
                rest = [m for m in filtered if m.get("category") not in category_boost]
                filtered = boosted + rest
            result = filtered[:n_results]
            log_search("okr_embeddings", query, result)
            return result
        except Exception:
            return []

    def sync_all_okrs(self, okrs: list[dict]) -> int:
        for okr in okrs:
            self.sync_okr(okr)
        return len(okrs)

    # ── MILESTONE SEMANTIC SEARCH ────────────────────────────────────

    def sync_milestone(self, milestone: dict) -> None:
        text = (
            f"{milestone.get('employee_id', '')} goal: "
            f"{milestone.get('raw_goal', '')} "
            f"SMART: {milestone.get('smart_goal') or milestone.get('raw_goal', '')}"
        )
        self.milestone_embeddings.upsert(
            ids=[milestone["id"]],
            documents=[text],
            metadatas=[
                {
                    "id": milestone["id"],
                    "employee_id": milestone.get("employee_id", ""),
                    "status": milestone.get("status", ""),
                }
            ],
        )

    def search_milestones(
        self,
        query: str,
        employee_id: str | None = None,
        n_results: int = 3,
    ) -> list[dict]:
        try:
            count = self.milestone_embeddings.count()
            if count == 0:
                return []
            where_filter = None
            if employee_id:
                where_filter = {"employee_id": {"$eq": employee_id}}
            results = self.milestone_embeddings.query(
                query_texts=[query],
                n_results=min(n_results * 2 if employee_id else n_results, count),
                where=where_filter,
            )
            if not results or not results.get("metadatas") or not results["metadatas"][0]:
                return []
            hits = results["metadatas"][0][:n_results]
            log_search("milestone_embeddings", query, hits)
            return hits
        except Exception:
            return []

    # ── POLICY DOCUMENT CHUNK SEARCH ─────────────────────────────────

    def ingest_policy_chunks(self, doc_id: str, chunks: list[dict]) -> int:
        if not chunks:
            return 0
        ids = []
        documents = []
        metadatas = []
        for chunk in chunks:
            chunk_id = f"{doc_id}_chunk_{chunk['chunk_index']}"
            ids.append(chunk_id)
            documents.append(chunk["text"])
            metadatas.append(
                {
                    "doc_id": doc_id,
                    "chunk_index": chunk["chunk_index"],
                    "section_title": chunk["section_title"],
                    "doc_title": chunk["doc_title"],
                    "filename": chunk["filename"],
                    "status": "active",
                }
            )
        self.policy_chunks.upsert(ids=ids, documents=documents, metadatas=metadatas)
        return len(chunks)

    def remove_policy_doc(self, doc_id: str) -> None:
        try:
            results = self.policy_chunks.get(where={"doc_id": {"$eq": doc_id}})
            if results and results.get("ids"):
                self.policy_chunks.delete(ids=results["ids"])
        except Exception:
            pass

    def update_policy_doc_status(self, doc_id: str, status: str) -> None:
        try:
            results = self.policy_chunks.get(where={"doc_id": {"$eq": doc_id}})
            if not results or not results.get("ids"):
                return
            for i, chunk_id in enumerate(results["ids"]):
                meta = dict(results["metadatas"][i])
                meta["status"] = status
                self.policy_chunks.update(ids=[chunk_id], metadatas=[meta])
        except Exception:
            pass

    def search_policy(
        self,
        query: str,
        n_results: int = 4,
        doc_id: str | None = None,
    ) -> list[dict]:
        try:
            count = self.policy_chunks.count()
            if count == 0:
                return []
            where_filter: dict = {"status": {"$eq": "active"}}
            if doc_id:
                where_filter = {
                    "$and": [
                        {"status": {"$eq": "active"}},
                        {"doc_id": {"$eq": doc_id}},
                    ]
                }
            results = self.policy_chunks.query(
                query_texts=[query],
                n_results=min(n_results, count),
                where=where_filter,
            )
            if not results or not results.get("documents") or not results["documents"][0]:
                return []
            output = []
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i]
                output.append(
                    {
                        "text": doc,
                        "section_title": meta.get("section_title", ""),
                        "doc_title": meta.get("doc_title", ""),
                        "filename": meta.get("filename", ""),
                        "doc_id": meta.get("doc_id", ""),
                        "chunk_index": meta.get("chunk_index", 0),
                    }
                )
            log_search("policy_chunks", query, output)
            return output
        except Exception:
            return []

    def count_policy_chunks(self, doc_id: str | None = None) -> int:
        try:
            if doc_id:
                results = self.policy_chunks.get(where={"doc_id": {"$eq": doc_id}})
                return len(results["ids"]) if results and results.get("ids") else 0
            return self.policy_chunks.count()
        except Exception:
            return 0

    # ── FEEDBACK EMBEDDINGS ───────────────────────────────────────────

    def sync_feedback_entry(self, entry: dict) -> None:
        entry_id = entry.get("entry_id") or entry.get("id")
        if not entry_id:
            return
        text = (
            f"{entry.get('feedback_type', 'general')}: "
            f"{entry.get('content') or entry.get('raw_text', '')}. "
            f"Context: {entry.get('context', '')}"
        )
        tags = entry.get("tags", [])
        tags_str = ",".join(tags) if isinstance(tags, list) else str(tags or "")
        self.feedback_embeddings.upsert(
            ids=[entry_id],
            documents=[text],
            metadatas=[
                {
                    "entry_id": entry_id,
                    "employee_id": entry.get("employee_id", ""),
                    "feedback_type": entry.get("feedback_type", "general"),
                    "sentiment": entry.get("sentiment", "neutral"),
                    "review_cycle": entry.get("review_cycle", ""),
                    "tags": tags_str,
                    "created_at": entry.get("created_at", ""),
                    "visibility": entry.get("visibility", "manager_only"),
                }
            ],
        )

    def remove_feedback_entry(self, entry_id: str) -> None:
        try:
            self.feedback_embeddings.delete(ids=[entry_id])
        except Exception:
            pass

    def search_feedback(
        self,
        query: str,
        employee_id: str | None = None,
        review_cycle: str | None = None,
        n_results: int = 5,
    ) -> list[dict]:
        try:
            count = self.feedback_embeddings.count()
            if count == 0:
                return []
            clauses: list[dict] = []
            if employee_id:
                clauses.append({"employee_id": {"$eq": employee_id}})
            if review_cycle:
                clauses.append({"review_cycle": {"$eq": review_cycle}})
            where_filter = None
            if len(clauses) == 1:
                where_filter = clauses[0]
            elif len(clauses) > 1:
                where_filter = {"$and": clauses}
            results = self.feedback_embeddings.query(
                query_texts=[query],
                n_results=min(n_results, count),
                where=where_filter,
            )
            if not results or not results.get("metadatas") or not results["metadatas"][0]:
                return []
            hits = results["metadatas"][0]
            log_search("feedback_embeddings", query, hits)
            return hits
        except Exception:
            return []

    def sync_all_feedback(self, entries: list[dict]) -> int:
        for entry in entries:
            self.sync_feedback_entry(entry)
        return len(entries)
