# 本地教材检索、审核图谱和微调

**续作已完成真实 Neo4j 入库和本地 Qwen 抽取：见 [REAL_RESULTS.md](REAL_RESULTS.md)。** 独立服务运行于 8011，411 条真实片段中 34 条 OCR 待复核、377 条可检索；真实三元组 30 条待审。

服务单独运行在 `127.0.0.1:8011`。未修改 backend 或 model-service 的 FastAPI 主应用。新增后端代码、工具和数据均位于本目录；小程序仅调整现有报告页和 Evidence 类型的出处展示，兼容原来源快照。

项目及上级目录未找到 AGENTS.md。所有命令从 `F:\code\tongue-analysis\tongue-analysis` 执行；通用 CLI 不自动读取主应用 `.env`，不会改动主应用数据库结构。续作 real.ps1 仅复用其中的 Neo4j 密码。Neo4j 使用独立 `Retrieval*` 标签。

## 首次交付记录（2026-11-19，续作前的历史状态）

- 本地 PDF：`E:\软件工程概论\DataSet\中医诊断学*.pdf`，236 页。版权页 PDF 第 2 页经本地 OCR 和页面图像核对：《中医诊断学》，第 5 版，中国中医药出版社，2021 年 6 月，李灿东、方朝义主编，ISBN 978-7-5132-6849-3。封面系列为新世纪第五版、全国高等中医药院校规划教材第十一版。
- 目录 PDF 第 13、14 页；原书书签只有 a1、a2 等编号，无法定位章节。正文 PDF 第 17 页对应印刷第 1 页。
- 舌诊选 PDF **55–71**（印刷 39–55）；问寒热/问汗选 **87–91**（印刷 71–75）；问饮食口味/问二便选 **99–104**（印刷 83–88）。根据边界页标题的纵坐标排除起止页的相邻小节。选页计划为 `textbook-plan.json`。
- 28 页选页均无可用文本层，才启用本地 RapidOCR。未 OCR 全书。28 个页眉均检测到印刷页码，保留页眉文本、坐标和识别置信度的审计文件。印刷页码来自识别，未经逐页人工复核；分段为版面启发式，正式印刷段落号全部 `null`。
- 得到 **411 个片段**，最长 337 字；原文、逐行坐标、OCR 置信度均在本地。PDF 第 **57、64** 页有低置信度 OCR 行，已写入 manifest 异常清单，仍需人工校对。表格、插图文字可能需要人工整理。
- 两个指定 BGE 模型已下载到 `models/`；已完成真实教材归一化向量生成：**411 × 512**。索引 ID：`8b63aa40026e070b33e62d0b`。
- 真实本地模型通过独立应用的 POST 接口验证：症状查询约 **8462 ms**，症状＋舌象约 **9572 ms**，候选 40、返回 5，本机 CPU。它们是单次连通性实测，不能作为质量或稳定性能结论。第二个查询首条出处 PDF 69 / 印刷 53。
- 9 项测试通过；小程序类型检查及微信小程序构建通过。训练模块导入验证通过，未执行真实训练。
- 本机 `127.0.0.1:7687` 连接被拒绝，**未进行真实 Neo4j 入库**。未发现可用的本地 Qwen 启动程序或监听服务，**未生成真实三元组**。尚无人工核对标注，**未生成真实检索质量指标、未微调**。

## 结果文件

| 文件 | 用途 |
|---|---|
| `data/inspection/page-002.png`、`.txt` | 版权页本地图片与 OCR |
| `data/inspection/page-013.png`、`page-014.png` | 目录核对 |
| `data/textbook/raw/*.txt` | 选中页原始全文，仅本地保存 |
| `data/textbook/pages/*.json` | 逐行文本、页面坐标和识别置信度 |
| `data/textbook/printed-page-audit.json` | 页眉印刷页码识别依据 |
| `data/textbook/chunks.jsonl` | 411 个可追溯片段 |
| `data/textbook/manifest.json` | 文件 SHA256、选页、异常及教材库指纹 |
| `data/index/{chunks.jsonl,vectors.npy,manifest.json}` | 固定教材与模型的向量快照 |
| `data/verification/symptoms.json`、`symptoms-tongue.json` | 真实请求与完整响应，非质量评估 |
| `samples/*.synthetic.*` | 明确标注的合成片段、审核候选、查询、响应、指标 |
| `label-template.jsonl` | 人工训练、验证、测试标注模板 |

`data/`、`models/` 和本地环境被忽略，不把教材原文与模型提交到源码库。所有片段的 `location` 保留章节、PDF 页序（从 1 开始）、印刷页码、段落号、页面文本块编号和 bbox。未知值保留 `null`；`block_on_page` 是程序分段编号，不能当作教材印刷段落号。chunk_id 由 PDF SHA256、页序、片段序号与原文计算；同一输入重复运行稳定，人工纠错后 ID 会更新，应重标相关引用。

## 环境与提取

本次 `research/retrieval/.venv` 使用本机 Anaconda 的现有 CPU PyTorch 2.10.0 和 sentence-transformers 5.2.2，通过 `--system-site-packages` 复用，新增依赖装在独立环境。新机器可直接建纯环境安装 requirements。

```powershell
Set-Location F:\code\tongue-analysis\tongue-analysis
python -m venv research\retrieval\.venv
$py = Join-Path $PWD 'research\retrieval\.venv\Scripts\python.exe'
& $py -m pip install -r research\retrieval\requirements.txt
$env:PYTHONIOENCODING = 'utf-8'
$pdf = (Get-ChildItem -LiteralPath 'E:\软件工程概论\DataSet' -Filter '中医诊断学*.pdf' | Select-Object -First 1).FullName
& $py -m research.retrieval inspect --pdf $pdf --out research/retrieval/data/inspection --pages '1-2,13-14' --ocr
& $py -m research.retrieval extract --pdf $pdf --plan research/retrieval/textbook-plan.json --out research/retrieval/data/textbook
```

首次 OCR 已随依赖提供本地识别模型，不使用云 OCR。`inspect` 输出逐页方法和行数；`extract` 输出范围、片段数、异常数、两条短样本。原文不会批量输出终端。使用匹配 PDF 指纹的本地逐页缓存可重复切分，避免重复 OCR。换书必须重新核对版权、目录、边界和印刷页码，不可沿用本计划。

首次获取指定模型（需要联网，只下载到项目）：

```powershell
& $py -c "from huggingface_hub import snapshot_download; snapshot_download('BAAI/bge-small-zh-v1.5',local_dir='research/retrieval/models/bge-small-zh-v1.5',allow_patterns=['*.json','*.txt','*.safetensors','*.model','1_Pooling/*']); snapshot_download('BAAI/bge-reranker-base',local_dir='research/retrieval/models/bge-reranker-base',allow_patterns=['*.json','*.txt','*.safetensors','*.model'])"
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_PROGRESS_BARS = '1'
$env:OMP_NUM_THREADS = '4'
$env:MKL_NUM_THREADS = '4'
& $py -m research.retrieval index --corpus research/retrieval/data/textbook/chunks.jsonl --index research/retrieval/data/index --embedding research/retrieval/models/bge-small-zh-v1.5 --batch-size 16
```

embedding 使用 BGE 中文查询前缀，教材原文不加前缀；批量编码并 L2 归一化。检索取候选后由 bge-reranker-base 计算 query/text 对得分。模型仅从本地加载，失败直接报错，不替换成假检索。索引包含教材指纹、模型文件指纹和向量校验值；embedding 变化时查询拒绝复用旧索引。

## 启动独立服务与接口

立即使用已生成的本地向量索引：

```powershell
$env:RETRIEVAL_EMBEDDING = 'research/retrieval/models/bge-small-zh-v1.5'
$env:RETRIEVAL_RERANKER = 'research/retrieval/models/bge-reranker-base'
$env:RETRIEVAL_BACKEND = 'local'
$env:RETRIEVAL_INDEX_PATH = 'research/retrieval/data/index'
& $py -m uvicorn research.retrieval.service:app --host 127.0.0.1 --port 8011
```

另开 PowerShell：

```powershell
$request = @{ symptoms='口渴，喜冷饮'; tongue_features='舌红，苔黄而干'; top_k=5; candidate_count=40 } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8011/v1/retrieve -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($request))
```

返回 `evidence`，每条包含 `chunk_id`、完整 `text`、`source_title`、`edition`、`location`、`score`、`vector_score`、`is_demo`。响应同时包含耗时、索引 ID、模型及候选数；空查询、超限输入、top_k 大于候选数返回 422。真实响应示例位置：

```json
{
  "chunk_id": "ch_600fc306cc5a9b620484b8a3",
  "source_title": "中医诊断学",
  "location": {
    "chapter": "上篇 / 第一章 望诊 / 第三节 舌诊",
    "pdf_page": 69,
    "printed_page": 53,
    "paragraph": null,
    "block_on_page": 5,
    "fragment_on_page": 5,
    "bbox": [68.0, 359.5, 509.5, 437.0],
    "paragraph_status": "layout_heuristic_requires_review"
  }
}
```

上面为位置字段节选；完整原文在 `data/verification/symptoms-tongue.json` 的 response.evidence 中。可重跑：

```powershell
& $py -m research.retrieval.verify_local
```

小程序现有报告页默认显示原文与书名，点“查看出处”展开位置及关系出处，未知段落显示“待核对”。原报告 `/reports/{id}/evidence` 路由没有改动；图文融合服务接入时，将独立服务 evidence 原样保存为报告快照，保留 chunk_id/location；旧 entity_id/title/kind/path 字段可由适配层补充。当前实现不会让历史报告自动改用本检索结果，也不绕过主服务去小程序直连本机端口。

## Neo4j 入库

可复用已有 Neo4j，或启动本目录独立实例（需 Docker 正常运行，首次拉取镜像需网络）：

```powershell
$env:NEO4J_PASSWORD = Read-Host '设置本地 Neo4j 密码'
docker compose -f research/retrieval/compose.yaml up -d
$env:NEO4J_URI = 'bolt://127.0.0.1:17687'
$env:NEO4J_USER = 'neo4j'
& $py -m research.retrieval ingest --index research/retrieval/data/index
$env:RETRIEVAL_BACKEND = 'neo4j'
$env:RETRIEVAL_INDEX_ID = '8b63aa40026e070b33e62d0b'
& $py -m uvicorn research.retrieval.service:app --host 127.0.0.1 --port 8011
```

按实际 ingest 输出设置 INDEX_ID。独立实例浏览器端口 17474、Bolt 17687，不占用主部署的 7474/7687。数据库保存 RetrievalSource、RetrievalChunk、RetrievalIndex、原文与完整位置，建立 cosine HNSW 向量索引并等待上线。按 index_id 使用独立向量属性，重建 embedding 不会删除旧片段和报告依据。入库可重跑。未提供自动删除历史索引命令。

## Qwen 候选、审核与发布

启动自己的本地 Qwen OpenAI 兼容服务，例如 Ollama 的 `/v1`。只允许 localhost/127.0.0.1/::1；片段通过本机接口送入 Qwen，禁用环境 HTTP 代理。每段请求只抽明确关系，要求逐字 quote 匹配对应 chunk。模型生成候选不能自动发布。若本地服务不支持 JSON response_format，会记录失败片段，可调整本地服务后重跑。

```powershell
& $py -m research.retrieval graph-extract --corpus research/retrieval/data/textbook/chunks.jsonl --out research/retrieval/data/review/candidates.jsonl --endpoint http://127.0.0.1:11434/v1 --model qwen2.5:7b
# 用编辑器审阅 candidates.jsonl，对照 chunk_id 查询原文；错误文件为 candidates.jsonl.errors.json
& $py -m research.retrieval review --file research/retrieval/data/review/candidates.jsonl --id 'rel_替换为实际候选ID' --status approved --reviewer '填写真实审核人'
& $py -m research.retrieval graph-import --corpus research/retrieval/data/textbook/chunks.jsonl --file research/retrieval/data/review/candidates.jsonl
$env:RETRIEVAL_REVIEW_FILE = 'research/retrieval/data/review/candidates.jsonl'
$env:RETRIEVAL_ADMIN_TOKEN = Read-Host '设置管理员接口令牌'
```

重新启动服务以读取环境变量。候选文件为独立审核事实源，串行审核，避免多人同时改同一文件。可用相同 review 命令改为 rejected 后重新 graph-import 撤销已发布关系。导入在事务中同步本教材的关系，只发布 approved 且有审核人/时间的候选，并核对 candidate_id、source_hash、原文 quote。所有关系保存 chunk_id、审核人和原文引文；节点通过 SUPPORTED_BY 关联同一教材片段。孤立历史节点不进入发布查询。

```powershell
$headers = @{ 'X-Admin-Token'=$env:RETRIEVAL_ADMIN_TOKEN }
Invoke-RestMethod http://127.0.0.1:8011/v1/admin/candidates -Headers $headers
Invoke-RestMethod http://127.0.0.1:8011/v1/admin/graph?limit=100 -Headers $headers
Invoke-RestMethod http://127.0.0.1:8011/v1/admin/chunks/ch_600fc306cc5a9b620484b8a3 -Headers $headers
Invoke-RestMethod http://127.0.0.1:8011/v1/graph?chunk_id=ch_600fc306cc5a9b620484b8a3
```

管理员 graph 返回 nodes、edges 及每条边完整 evidence；public `/v1/graph` 只查已审核发布关系。管理员候选与出处查询需要令牌，未配置令牌时拒绝访问。本地向量后端不冒充数据库图谱，图谱接口返回 503。

## 标注、评估和训练

复制 label-template.jsonl 到本地文件。每行包含 query_id、split、symptoms、tongue_features、relevant_chunk_ids、hard_negative_chunk_ids、human_verified、reviewer。用真实 chunk_id 标注相关与易混淆片段，人工核对后设 human_verified=true 并填写 reviewer。保留独立 validation/test 查询；相同症状查询不得跨 split，不要将测试查询改写后用于训练。测试集不参与训练或模型选择。

先固定教材库、base 模型和候选数运行基线。评估会暖机后分别测“只用症状”“症状＋舌象”，同时报告 vector 与 reranked 的 Recall@K、MRR@K、每条查询耗时和平均耗时。MRR 为截断在 K 的 MRR@K；耗时包含查询编码、候选检索和重排序，不含启动加载。评估使用固定的本地向量快照，不将 ANN 差异混入输入模式对比。

```powershell
& $py -m research.retrieval evaluate --index research/retrieval/data/index --labels research/retrieval/data/labels.human.jsonl --out research/retrieval/data/evaluation.base.json --embedding research/retrieval/models/bge-small-zh-v1.5 --reranker research/retrieval/models/bge-reranker-base --k 5 --candidates 40 --split test
```

人工样本尚未提供，上述真实评估不能运行。`samples/evaluation.synthetic.json` 仅证明指标计算/对比流程，不说明中医检索效果。它使用 3 维合成编码器、3 个伪片段，不能与 BGE 结果比较。

收到核对后的 train/validation 后运行：

```powershell
# embedding：query/positive/hard-negative TripletLoss
& $py -m research.retrieval train embedding --corpus research/retrieval/data/textbook/chunks.jsonl --labels research/retrieval/data/labels.human.jsonl --out research/retrieval/data/training/embedding-v1 --model research/retrieval/models/bge-small-zh-v1.5 --epochs 1 --batch-size 8
# embedding 改变必须重建教材向量并重新入库，保留原索引用于比较
& $py -m research.retrieval index --corpus research/retrieval/data/textbook/chunks.jsonl --index research/retrieval/data/index-embedding-v1 --embedding research/retrieval/data/training/embedding-v1/final
& $py -m research.retrieval ingest --index research/retrieval/data/index-embedding-v1

# reranker：positive=1 / hard-negative=0 BinaryCrossEntropyLoss
& $py -m research.retrieval train reranker --corpus research/retrieval/data/textbook/chunks.jsonl --labels research/retrieval/data/labels.human.jsonl --out research/retrieval/data/training/reranker-v1 --model research/retrieval/models/bge-reranker-base --epochs 1 --batch-size 8
# 仅改 reranker 时复用原 embedding 索引
& $py -m research.retrieval evaluate --index research/retrieval/data/index --labels research/retrieval/data/labels.human.jsonl --out research/retrieval/data/evaluation.reranker-v1.json --embedding research/retrieval/models/bge-small-zh-v1.5 --reranker research/retrieval/data/training/reranker-v1/final --k 5 --candidates 40
```

训练拒绝未审核样本、未知片段、正负交叉、跨集合重复查询、缺失验证集、合成数据和覆盖已有非空输出目录。训练 seed=42，用验证 loss 选择模型，保存 final 与教材/标注指纹。调 embedding 后服务必须同时更新 EMBEDDING 与 INDEX_ID；单调 reranker 只更新 RERANKER，保持索引不变。CPU 可运行但速度慢，真实训练耗时尚未测量。

## 本地验证

```powershell
& $py -m research.retrieval.demo
& $py -m pytest research/retrieval/tests -q
Push-Location miniapp
npm run typecheck
npm run build:mp-weixin
Pop-Location
```

合成候选默认 pending，合成样本永远不会被用于真实微调。本次测试覆盖稳定提取、文本层优先、未知位置、索引指纹、输入校验、空管理员令牌、图谱候选来源校验、发布过滤/撤销、指标计算、留出查询与训练审核门槛。Neo4j Cypher 的真实执行和本地 Qwen 调用仍待服务可用后验证。

实现参考：[Neo4j 向量索引](https://neo4j.com/docs/genai/tutorials/current/embeddings-vector-indexes/setup/vector-index/)、[Neo4j 内置向量查询](https://neo4j.com/docs/operations-manual/current/procedures/built-in-procedures/)、[Sentence Transformers 重排序训练](https://sbert.net/docs/cross_encoder/training_overview.html)。
