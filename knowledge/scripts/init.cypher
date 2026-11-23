// Execute on Neo4j 5.26+. Does not delete existing graph data.
CREATE CONSTRAINT knowledge_entity_id IF NOT EXISTS FOR (n:KnowledgeEntity) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT knowledge_source_id IF NOT EXISTS FOR (s:Source) REQUIRE s.id IS UNIQUE;
CREATE INDEX knowledge_entity_name IF NOT EXISTS FOR (n:KnowledgeEntity) ON (n.name);
CREATE INDEX knowledge_entity_kind IF NOT EXISTS FOR (n:KnowledgeEntity) ON (n.kind);
CREATE INDEX knowledge_entity_status IF NOT EXISTS FOR (n:KnowledgeEntity) ON (n.status);
CREATE INDEX knowledge_relation_id IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON (r.id);
