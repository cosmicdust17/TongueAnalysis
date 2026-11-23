import json
import os
from pathlib import Path
from .io_utils import read_json, rows


class NeoStore:
    def __init__(self):
        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]), connection_timeout=5)
        self.database = os.getenv("RETRIEVAL_NEO4J_DATABASE", "neo4j")
        self.driver.verify_connectivity()

    def run(self, cypher, **params):
        return [r.data() for r in self.driver.execute_query(cypher, parameters_=params, database_=self.database).records]

    def close(self):
        self.driver.close()

    def ingest(self, path):
        import numpy as np
        from .io_utils import digest, file_hash
        path = Path(path)
        manifest, chunks = read_json(path / "manifest.json"), rows(path / "chunks.jsonl")
        if digest(chunks) != manifest['corpus_hash'] or file_hash(path / 'vectors.npy') != manifest['vectors_hash']:
            raise ValueError('Changed index artifacts')
        vectors = np.load(path / "vectors.npy", allow_pickle=False)
        if vectors.shape != (len(chunks), int(manifest['dimension'])) or not np.isfinite(vectors).all():
            raise ValueError('Invalid vector shape or values')
        from .quality import quality
        for label, prop in [("RetrievalChunk", "chunk_id"), ("RetrievalSource", "source_id"),
                            ("RetrievalIndex", "index_id"), ("RetrievalEntity", "entity_id")]:
            self.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE")
        # Versioned vector properties isolate rebuilt embedding indexes without deleting old evidence.
        index = "retrieval_" + manifest["index_id"]
        dim = int(manifest["dimension"])
        self.run(f"CREATE VECTOR INDEX {index} IF NOT EXISTS FOR (c:RetrievalChunk) ON c.{index} "
                 f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dim}, `vector.similarity_function`: 'cosine'}}}}")
        for offset in range(0, len(chunks), 100):
            batch = []
            for c, vector in zip(chunks[offset:offset+100], vectors[offset:offset+100]):
                flags = quality(c)
                batch.append({"chunk_id": c["chunk_id"], "text": c["text"], "source_id": c.get("pdf_sha256", "demo"),
                              "source_title": c["source_title"], "edition": c.get("edition"),
                              "location_json": json.dumps(c["location"], ensure_ascii=False),
                              "payload": json.dumps(dict(c, **flags), ensure_ascii=False), "vector": vector.tolist(),
                              "eligible_vector": vector.tolist() if flags['retrieval_eligible'] else None,
                              'is_test': bool(c.get('is_demo')),
                              **flags, 'chapter': c['location'].get('chapter'),
                              'pdf_page': c['location'].get('pdf_page'), 'printed_page': c['location'].get('printed_page'),
                              'paragraph': c['location'].get('paragraph')})
            self.run(f"UNWIND $batch AS b MERGE (s:RetrievalSource {{source_id:b.source_id}}) "
                     "SET s.title=b.source_title, s.edition=b.edition "
                     "MERGE (c:RetrievalChunk {chunk_id:b.chunk_id}) "
                     f"SET c.text=b.text, c.location_json=b.location_json, c.payload=b.payload, c.{index}_raw=b.vector, "
                     f"c.{index}=b.eligible_vector, c.retrieval_eligible=b.retrieval_eligible, c.ocr_status=b.ocr_status, "
                     "c.chapter=b.chapter,c.pdf_page=b.pdf_page,c.printed_page=b.printed_page,c.paragraph=b.paragraph,c.is_test=b.is_test "
                     "MERGE (c)-[:FROM_SOURCE]->(s)", batch=batch)
        self.run("CALL db.awaitIndex($name, 300)", name=index)
        self.run("MERGE (i:RetrievalIndex {index_id:$id}) SET i.manifest=$manifest",
                 id=manifest["index_id"], manifest=json.dumps(manifest))
        return manifest

    def graph(self, chunk_id=None, limit=100, include_test=False):
        results = self.run("MATCH (a:RetrievalEntity)-[r:RETRIEVAL_RELATION]->(b:RetrievalEntity) "
            "MATCH (c:RetrievalChunk {chunk_id:r.chunk_id}) "
            "WHERE r.approved=true AND c.retrieval_eligible=true AND (coalesce(c.is_test,false)=false OR $include_test) "
            "AND ($chunk IS NULL OR r.chunk_id=$chunk) "
            "RETURN properties(a) AS source, properties(b) AS target, properties(r) AS relation, c.payload AS evidence "
            "ORDER BY r.candidate_id LIMIT $limit", chunk=chunk_id, limit=limit, include_test=include_test)
        return [dict(v, evidence=json.loads(v["evidence"])) for v in results]


class NeoIndex:
    backend = 'neo4j'
    def __init__(self, store, index_id, models):
        if len(index_id) != 24 or any(c not in "0123456789abcdef" for c in index_id):
            raise ValueError("Invalid index ID")
        result = store.run("MATCH (i:RetrievalIndex {index_id:$id}) RETURN i.manifest AS manifest", id=index_id)
        if not result:
            raise ValueError("Index not ingested")
        self.manifest = json.loads(result[0]["manifest"])
        if self.manifest["embedding_identity"] != models.identity:
            raise ValueError("Embedding changed; rebuild index")
        self.store, self.models = store, models

    def candidates(self, query, count):
        found = self.store.run("CALL db.index.vector.queryNodes($name,$count,$vector) YIELD node,score "
                               "WHERE node.retrieval_eligible=true AND coalesce(node.is_test,false)=false "
                               "RETURN node.payload AS payload,score", name="retrieval_" + self.manifest["index_id"],
                               count=count, vector=self.models.encode([query], query=True)[0].tolist())
        return [dict(json.loads(r["payload"]), vector_score=r["score"]) for r in found]
