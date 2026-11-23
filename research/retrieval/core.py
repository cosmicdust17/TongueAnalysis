import os
from pathlib import Path
from .io_utils import digest, file_hash, read_json, rows, write_json

QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


def query_text(symptoms, tongue_features=None):
    parts = []
    if symptoms and symptoms.strip():
        parts.append("症状：" + symptoms.strip())
    if tongue_features and tongue_features.strip():
        parts.append("舌象：" + tongue_features.strip())
    if not parts:
        raise ValueError("symptoms and tongue_features cannot both be empty")
    return "；".join(parts)


def model_identity(name):
    path = Path(name)
    if not path.is_dir():
        from huggingface_hub import snapshot_download
        path = Path(snapshot_download(name, local_files_only=True))
    return digest([(str(p.relative_to(path)), file_hash(p)) for p in sorted(path.rglob('*'))
                   if p.is_file() and '.cache' not in p.relative_to(path).parts])


class Models:
    def __init__(self, embedding=None, reranker=None):
        from sentence_transformers import SentenceTransformer
        self.embedding_name = embedding or os.getenv("RETRIEVAL_EMBEDDING", "BAAI/bge-small-zh-v1.5")
        self.reranker_name = reranker or os.getenv("RETRIEVAL_RERANKER", "BAAI/bge-reranker-base")
        # Offline by default: explicitly download models before running a local service.
        self.encoder = SentenceTransformer(self.embedding_name, local_files_only=True)
        self.reranker = None
        self.identity = model_identity(self.embedding_name)

    def load_reranker(self):
        if self.reranker is None:
            from sentence_transformers import CrossEncoder
            self.reranker = CrossEncoder(self.reranker_name, local_files_only=True, max_length=512)

    def encode(self, texts, query=False, batch_size=32):
        return self.encoder.encode([QUERY_PREFIX + t if query else t for t in texts],
                                   batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)

    def rank(self, query, candidates, k):
        if not candidates:
            return []
        self.load_reranker()
        scores = self.reranker.predict([(query, c["text"]) for c in candidates], show_progress_bar=False)
        return sorted([dict(c, score=float(s)) for c, s in zip(candidates, scores)],
                      key=lambda c: (-c["score"], c["chunk_id"]))[:k]


def build_vectors(corpus, out, models, batch_size=32):
    import numpy as np
    chunks = rows(corpus)
    if not chunks or len({c['chunk_id'] for c in chunks}) != len(chunks):
        raise ValueError("Corpus must be nonempty with unique chunk IDs")
    vectors = models.encode([c["text"] for c in chunks], batch_size=batch_size)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "vectors.npy", vectors)
    from .io_utils import write_rows
    write_rows(out / "chunks.jsonl", chunks)
    manifest = {"corpus_hash": digest(chunks), "embedding": models.embedding_name,
                "embedding_identity": models.identity, "dimension": int(vectors.shape[1]),
                "count": len(chunks), "vectors_hash": file_hash(out / "vectors.npy")}
    manifest["index_id"] = digest(manifest)[:24]
    write_json(out / "manifest.json", manifest)
    return manifest


class LocalIndex:
    """Explicit offline exact-vector backend; never silently substituted for Neo4j."""
    def __init__(self, path, models):
        import numpy as np
        path = Path(path)
        self.manifest = read_json(path / "manifest.json")
        self.chunks = rows(path / "chunks.jsonl")
        if digest(self.chunks) != self.manifest["corpus_hash"] or file_hash(path / "vectors.npy") != self.manifest["vectors_hash"]:
            raise ValueError("Index artifacts changed; rebuild index")
        if models.identity != self.manifest["embedding_identity"]:
            raise ValueError("Embedding changed; rebuild index before querying")
        self.vectors = np.load(path / "vectors.npy", allow_pickle=False)
        self.models = models

    def candidates(self, query, count):
        from .quality import quality
        scores = self.vectors @ self.models.encode([query], query=True)[0]
        eligible = [i for i in scores.argsort()[::-1] if quality(self.chunks[i])['retrieval_eligible']][:count]
        return [dict(self.chunks[i], **quality(self.chunks[i]), vector_score=float(scores[i])) for i in eligible]


def retrieve(index, models, symptoms, tongue_features, count=40, k=5):
    import time
    started = time.perf_counter()
    query = query_text(symptoms, tongue_features)
    candidates = index.candidates(query, count)
    retrieved = time.perf_counter()
    evidence = models.rank(query, candidates, k)
    return {"evidence": evidence, "elapsed_ms": round((time.perf_counter()-started)*1000, 3),
            "timings": {"embedding_search_seconds": retrieved-started,
                        "rerank_seconds": time.perf_counter()-retrieved},
            "backend": getattr(index, 'backend', 'local'),
            "index_id": index.manifest["index_id"], "candidate_count": count,
            "embedding": models.embedding_name, "reranker": models.reranker_name}
