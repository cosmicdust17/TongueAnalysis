# 真实 Neo4j 与教材三元组交付

## 本轮人工审核批量发布

本批在真实 Neo4j 新增 24 条教材关系。首次发布前有 0 条真实教材关系，复跑新增 0 条，24 条关系的 Neo4j ID、属性和出处一致。独立的合成验收关系仍隔离。20 条按修订版发布，4 条沿用原案。2 条重复关系已合并，2 条排除，2 条待拆分复审，所含 8 条草案随父条目暂缓发布。

当前审核表、发布清单、发布结果、公开接口响应和管理员接口响应保存在 `data/review-audit/round-update`。重点关系使用 `rel_fac815a69cc0c5cab65e05d1`。图谱关系为“可见于”，限定为“部分”，适用条件为“外感病见之”。原书措辞仅保留在引文。可按 `ch_da6bd816d1d39d82b8367bb1` 查询出处。

已经批准的同一批清单可用现有发布入口重跑：

```powershell
.\research\retrieval\real.ps1 -Action Publish `
  -ReviewFile '.\research\retrieval\data\review-audit\round-update\publish-candidates.jsonl'
```

## 2026-11-23 教材核对与管理员图谱验收

审核表为 `data/review-audit/舌诊教材三元组审核表.xlsx`。已逐条对照原书截图、入库片段、引用和证据 ID。30 条候选的机器建议为保留 4 条、修订 20 条、拆分后再审 2 条、不采纳 4 条。30 条真实候选全部待审，真实图谱发布数为 0。原书第 47 页的强硬舌特征段中，OCR 把“语言蹇涩”识别成了“语言骞涩”。该行建议引用前面的清晰文字。PDF 第 57、64 页继续按原规则隔离。

请在“候选审核”工作表的浅黄色栏填写人工决策、审核人和可选备注。“教材出处”按同一候选 ID 列出原案与修订引文。填写示例为 `批准修订`、`张三`、`已对照书页，保留“常见于”`。留空会保留当前状态。人工决策适用 `批准原案`、`批准修订`、`不批准／撤销`。保存后，从项目目录执行：

```powershell
.\research\retrieval\real.ps1 -Action Publish `
  -ReviewWorkbook '.\research\retrieval\data\review-audit\舌诊教材三元组审核表.xlsx'
```

撤销时在同一行选择 `不批准／撤销`，保留审核人并再次执行。表中的修订从本轮核对记录读取，发布时仍使用原候选 ID 和证据 ID。

小程序知识库管理员的图谱页新增“教材知识图谱”。当前主应用配置通过 `RETRIEVAL_GRAPH_BASE_URL=http://127.0.0.1:8014` 访问独立 Neo4j 图谱服务。重新启动时可运行 `.\research\retrieval\real.ps1 -Action Serve -Port 8014`。图谱页从主应用读取已发布教材关系。点击节点后显示相连关系和来源，点击边或关系行后展示原文、引用、页码和证据 ID。

浏览器验收通过实际管理员接口查到真实空状态，并用隔离的合成响应验证了节点与边点击、证据弹层和普通用户 403 权限。Neo4j 的合成关系连续发布两次仍只有 1 条，支持引文和教材片段使用同一证据 ID，撤销后管理员查询返回空。截图和验收结果在 `data/review-audit` 下。小程序 H5、微信构建通过，后端与检索套件分别通过 50 和 13 项测试。

## 2026-11-19 入库与候选抽取记录

工作目录为 `F:\code\tongue-analysis\tongue-analysis`。本节记录首次真实入库和模型抽取时的配置与结果。

## 实测结果

| 项目 | 实际结果 |
|---|---|
| Neo4j | Community 5.26.33，RETURN 1 返回 1 |
| 连接 | bolt://127.0.0.1:17687；Browser http://127.0.0.1:17474 |
| 实例 | Docker 项目 tongue-retrieval，容器 tongue-retrieval-retrieval-neo4j-1，独立持久卷 |
| 真实教材 | 1 个来源、411 个稳定 chunk_id，全部原文/出处/已有 512 维向量入库 |
| OCR 隔离 | PDF 57、64 两页共 34 个片段，保守按整页标为 pending_review；377 个可对外检索 |
| 向量索引 | retrieval_8b63aa40026e070b33e62d0b，ONLINE，populationPercent=100，512 维 cosine |
| 重复导入 | 连续两次均 411 条；引用 ID 集合 SHA256 均为 85dee26ac9c499ec46ca5f4e3a184de832e06b56419f89e78adbe5289d0a2c72 |
| 真实 HTTP | POST /v1/retrieve 返回 200、backend=neo4j、5 条证据；逐条用管理员出处接口核对原文和位置 |
| Qwen | 复用已跑通的 Qwen3-VL-2B-Instruct，既有 multimodal 环境和 E 盘本地缓存；RTX 4060，NF4 4-bit，全程离线 |
| 真实批次 | 12 个舌诊片段，30 条候选通过逐字原句校验；5 条不匹配引文被拒绝，见 run.json |
| 条件和限定 | 保存 condition、condition_origin、qualifiers；4 条含原文条件，保留“常见”“多见”“多为”“不能”等原句限定 |
| 真实发布 | 30 条全部 pending，实际发布入口校验 approved=0；生产图谱没有真实已审关系 |
| 发布验收 | 1 条明确标注的合成测试关系，在真实 Neo4j 验证待审过滤、批准发布、出处定位、撤销、重新发布；默认生产查询排除它 |
| 回归测试 | 13 项通过；最终 real.ps1 -Action Verify 和实际 Neo4j 合成发布流程均已复跑成功 |

Docker Desktop 最初未启动，原 7687 和独立 17687 均拒绝连接。后台启动 Docker 后使用独立配置创建 Neo4j；保留已有其他容器、卷和数据库内容。新实例导入前节点数为 0。当前另保留 **1 个合成测试片段、2 个合成实体和 1 条合成关系**，以 `is_test/is_demo` 和独立 ID 隔离，不能混入上述 411 条真实教材统计。

原始向量始终保留于每条节点的版本化 `_raw` 属性；只有通过 OCR 隔离策略的片段才有供公开索引使用的向量属性。查询还再次检查 retrieval_eligible，避免待复核片段进入重排序。原始 chunks.jsonl、vectors.npy 和原索引指纹均未改动。没有把“不被低置信度规则标记”写成“人工已核对”。

## 可直接查看的本地交付

- `data/acceptance/ingest.json`：RETURN 1、Neo4j 版本、两次计数/引用 ID、索引配置和 ONLINE 状态。
- `data/acceptance/http.json`：真实 HTTP 请求和完整响应、管理员候选、默认管理员图谱、单独查询的已发布测试关系。
- `data/qwen-batch/review.csv`：UTF-8 BOM，供人工核对的 30 条候选；含三元组、条件、限定语、支持句、完整片段、书名、版次、页码、章节、chunk_id、审核状态和核对提示。
- `data/qwen-batch/candidates.jsonl`：审核事实源，保留原术语与归一术语、来源指纹、模型 revision。CSV 是阅读导出，不把 CSV 修改自动当成审核。
- `data/qwen-batch/run.json`、`raw/*.json`、`selected-chunks.jsonl`：模型原始输出、12 个输入片段、逐段记录与拒绝详情。
- `data/ocr-pending.jsonl`：34 条隔离片段及完整位置。
- `data/acceptance/real-publication.json`：真实候选审核发布校验结果（0/30）。
- `data/acceptance/publication.synthetic.json`：真实数据库中的独立合成发布流程验收，明确 is_demo=true。

所有教材文本、候选、令牌和运行产物仍只在本地 data 下。30 条只是候选，**字面引文匹配不等于医学语义正确**；其中 25 条附有主体需结合标题或谓词措辞需核对的提示，必须人工逐条审阅。空 condition 表示原句未明确提供或仍需核对，不能解读为无适用限制。段落号仍为 null，保留 block_on_page/bbox，不伪造印刷段落。

## 一组真实检索

独立服务现在运行于 http://127.0.0.1:8011 ，接口说明 http://127.0.0.1:8011/docs 。

```powershell
Set-Location F:\code\tongue-analysis\tongue-analysis
$body = @{symptoms='口渴，喜冷饮'; tongue_features='舌红，苔黄而干'; top_k=5; candidate_count=40} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8011/v1/retrieve -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

实际响应为 backend=neo4j、5 条原文证据。首条 chunk_id 为 `ch_600fc306cc5a9b620484b8a3`，书名《中医诊断学》，PDF 第 69 页、印刷第 53 页、页面文本块 5。完整 text 原样保存在 http.json 中，没有用模型生成的摘要替换引文。耗时记录在 response.elapsed_ms，属于单次联通性实测，不是检索质量评估。

候选示例：`歪斜舌 → 多见于 → 中风或中风先兆`，支持原句“多见中风或中风先兆。”，出处 chunk `ch_2535bfdd452925c74e4790a8`、PDF 63、印刷 47，qualifiers=["多见"]，状态 pending。主体由同一片段标题提供，清单已提示人工结合标题核对。

## 可复跑命令

```powershell
Set-Location F:\code\tongue-analysis\tongue-analysis
# Docker Desktop 已运行；重复 up 不删除卷
.\research\retrieval\real.ps1 -Action Neo4j
# 重复导入两次并核对 411 个真实 ID，已有向量直接复用
.\research\retrieval\real.ps1 -Action Ingest
# 复用此前本地模型；已生成片段复用 raw 缓存，只解析和校验，不重复推理
.\research\retrieval\real.ps1 -Action Extract -Limit 12
# 本次已后台启动，不要再占用同一端口；重启机器后在单独终端运行
.\research\retrieval\real.ps1 -Action Serve
```

另一个终端执行验收：

```powershell
.\research\retrieval\real.ps1 -Action TestPublication
.\research\retrieval\real.ps1 -Action Verify
```

real.ps1 默认复用 `.env` 中已有的 NEO4J_PASSWORD，仅用于独立实例；不修改该文件。可通过 NEO4J_URI、NEO4J_USER、NEO4J_PASSWORD、RETRIEVAL_NEO4J_DATABASE 覆盖以复用其他实例。后台服务 PID 和日志在 data/service.pid、service.stdout.log、service.stderr.log。管理员令牌自动保存在 data/admin-token.txt，不会写入终端、结果报告或源代码。

## 管理员关系和出处查询

```powershell
$token = (Get-Content -LiteralPath research\retrieval\data\admin-token.txt -Raw).Trim()
$headers = @{'X-Admin-Token'=$token}
# 默认只展示已审核真实关系，目前为空
Invoke-RestMethod http://127.0.0.1:8011/v1/admin/graph -Headers $headers
# 显式查询独立合成测试关系，目前为 1 条；生产接口不能打开此选项
Invoke-RestMethod 'http://127.0.0.1:8011/v1/admin/graph?include_test=true&chunk_id=retrieval-acceptance-test-v1' -Headers $headers
# 关系 evidence/关系上的 chunk_id 与出处查询使用同一 ID
Invoke-RestMethod http://127.0.0.1:8011/v1/admin/chunks/retrieval-acceptance-test-v1 -Headers $headers
Invoke-RestMethod http://127.0.0.1:8011/v1/admin/chunks/ch_2535bfdd452925c74e4790a8 -Headers $headers
Invoke-RestMethod http://127.0.0.1:8011/v1/admin/candidates -Headers $headers
```

关系查询返回 nodes/edges，每条边带 relation.chunk_id 和完整 evidence。沿用现有小程序“查看出处”所使用的 chunk_id/location 格式，无需修改图文融合主应用。当前小程序业务路由、报告引用接入仍按原有独立检索约定调用。

## 人工核对后再公开

```powershell
$py = '.\research\retrieval\.venv\Scripts\python.exe'
# 由真实审核人操作；替换示例 ID 和姓名。当前交付没有执行真实关系批准。
& $py -m research.retrieval review --file research/retrieval/data/qwen-batch/candidates.jsonl --id 'rel_实际候选ID' --status approved --reviewer '实际审核人'
.\research\retrieval\real.ps1 -Action Publish
# 撤销：同一候选标记 rejected 后再 Publish
```

发布只同步审核文件中的 candidate_id，保留其他批次和其他数据库内容。文件移除候选不表示撤销，必须显式标记 rejected 再发布。

OCR 隔离片段只有在核对 PDF 图像、确认原文正确后才能批准：

```powershell
& $py -m research.retrieval.review_ocr --chunk-id 'ch_实际待复核片段ID' --status approved --reviewer '实际审核人'
.\research\retrieval\real.ps1 -Action Ingest
```

人工批准绑定原片段指纹，原文变化后失效。如果需修改 OCR 原文，按原提取/向量流程生成新 chunk_id 和新索引，不能批准旧片段后静默替换文字。
