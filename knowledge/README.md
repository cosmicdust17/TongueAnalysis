# 知识图谱数据

- sources/：保存你有权使用的原始文献、教材或资料；实际上传文件由后端保存到storage/documents。
- processed/demo-graph.json：明确标注为示例的联调数据，无临床结论。
- schemas/graph.schema.json：交换文件结构。
- scripts/init.cypher 与 init_graph.py：Neo4j约束和索引初始化。
- scripts/import_graph.py：JSON批量校验与导入，单事务提交，不覆盖已有ID。

导入格式含sources、nodes、relations三个数组，所有ID长度不超过36，且不可与现有数据冲突。实体kind为舌象特征/症状/证候；关系kind为相关/伴随/支持。每个实体和关系必须有source_id。aliases保存同义词。

```powershell
# 在项目根目录，使用已安装后端依赖的Python
python knowledge/scripts/import_graph.py your-graph.json
```

导入实体和关系统一进入pending状态，需从知识管理员端审核发布后才用于检索。图谱示例seed通过独立命令加载，可直接演示已发布数据。文档上传只是保存来源，不会自动抽取或训练。
