# 真实端到端联调验收（2026-11-20）

项目根目录：`F:\code\tongue-analysis\tongue-analysis`。项目及父目录未发现 AGENTS.md，保留已有页面、登录、MySQL、模型 HTTP 适配器与 PDF 流程。

## 实际执行范围

在微信开发者工具的 `miniapp/dist/build/mp-weixin` 中执行上传页、输入症状、提交、报告展示、历史重开与导出按钮。使用隔离的开发联调普通用户，未合并任何微信账号历史。

为可重复验收，只有 `wx.chooseImage` 的选择结果替换为项目内已有的真实拍摄舌照（441×445）；不是现场拍摄。后续 `uni.uploadFile`、FastAPI、MySQL、YOLO、BGE、Qwen、报告与 PDF 全部真实运行，未 mock 推理或检索结果。框/标签及出处的 view 元素通过其实际绑定的 tap 处理器验证；按钮、文本输入和历史卡片通过开发者工具页面自动化执行。触摸命中区域仍需真机复测。

验收症状：`近一周口干、乏力，睡眠较浅`，持续时间近一周。症状为联调输入，并不代表原图拍摄者的真实病情。

报告：`35759b4f-47aa-46a0-a30e-6dc1095c2352`；任务：`a167db98-2d7b-4c8b-b56b-85975508b786`。模型是 clean_v1，检出一个白苔框；裂纹未出框，显示“未检出裂纹特征”。本报告只证明系统联通，不证明医学质量或检出准确性。

## 配置与实际服务

- 8000：现有 FastAPI；读取项目 `.env` 后读取上级 `F:\code\tongue-analysis\.env`，进程环境优先。
- 8002：现有 HTTP 模型服务，clean_v1 YOLO11n + 本地 `Qwen/Qwen3-VL-2B-Instruct`，GPU NF4，未训练。Qwen revision `89644892e4d85e24eaac8bacfd4f463576704203`。
- YOLO 权重：`research/results/formal/clean-v1-yolo11n-seed42/weights/best.pt`；640 / 0.218。
- 权重 SHA256：`4455a8217b44db4f63da7d52c593698528f310c4269a12a9c429d32fdc88f5a6`。
- 8011：复用已运行的本地 BGE embedding + reranker 服务及现有 Neo4j 索引；未重新导入或发布知识图谱。索引 ID `8b63aa40026e070b33e62d0b`。
- 根 `.env` 已设置 `MULTIMODAL_ENABLED=true`、`MODEL_BASE_URL=http://127.0.0.1:8002`、`KNOWLEDGE_RETRIEVAL_ENABLED=true`、`RETRIEVAL_BASE_URL=http://127.0.0.1:8011`、`RETRIEVAL_TIMEOUT_SECONDS=30`、`MODEL_TIMEOUT_SECONDS=240`、`RETRIEVAL_REQUIRE_REVIEWED=true`、`QWEN_OFFLINE=true`、`QWEN_MAX_NEW_TOKENS=512`。

## 改动与结果来源

| 文件 | 行为 |
|---|---|
| `model-service/predictor.py`、`model-service/app.py` | 绑定图片摘要的检测快照；先检测，再将同一份检测交给 Qwen，避免重复 YOLO 推理产生不同结果 |
| `backend/app/integrations/inference/http.py` | YOLO→BGE→Qwen；校验合法 chunk_id，锁定原检测结果，记录分阶段耗时 |
| `backend/app/services/result_integrity.py`、`backend/app/integrations/generation/generator.py` | 检测框与特征栏都由已保存检测构造；视觉及相关诊断性生成描述隔离为待复核，不覆盖检测事实 |
| `backend/app/services/analysis_service.py` | 同一报告保存图、框、症状摘要、分析、引用、版本、阶段耗时；保留 analyses 原始模型结果 |
| `backend/app/core/config.py`、`backend/app/integrations/retrieval/http.py` | 检索发布前校验本地审核清单和原文+书名+位置 SHA256；排除未审与低置信 OCR |
| `research/multimodal/contracts.py`、`runtime.py` | report 模式只整理症状、保存的检测和证据；严格 JSON 与引用校验，调整输出上限和防重复生成参数 |
| `research/retrieval/quality.py`、`research/retrieval/data/source-review.json` | 来源审核元数据与 5 条原书文字核对记录；不代表临床专家审核 |
| `miniapp/src/pages/report/index.vue`、`miniapp/src/types/index.ts` | 展示待复核观察；复用现有标注组件、出处弹层与导出流程 |
| `backend/app/services/export_service.py`、`backend/app/api/reports.py` | PDF 同一带框原图、解释、待复核观察与保存引用；可读出处；记录导出耗时头 |
| `backend/tests/test_result_integrity.py`、`backend/tests/conftest.py` | 冲突隔离、审核门禁、单次检测绑定检查；测试环境不请求真实模型或用户数据库 |
| `scripts/verify_real_e2e.py` | 重复导出、图片原始资源逐像素比对、原文比对、MySQL 归属与模型结果只读核对 |

本次 Qwen 虽输出合法 JSON，仍出现检测未确认的青紫舌及额外症状/证候推断。这些内容实际保存在待复核区，并在页面和 PDF 明示不作为已确认检测结果。当前不是可自动发布医学结论的版本。正文仅保留已保存 YOLO 事实；原用户症状保存在 analyses，不被生成摘要覆盖。

## 真实引用与 OCR

5 条引用均由 Qwen 返回合法 chunk_id，再由后端取检索原文、书名和位置快照，未采用 Qwen 编造引文。已逐条对照渲染的原书页面；原书来自本机《中医诊断学》第5版。核对范围是文字与来源一致性，非临床适用性。

可复核实例：`ch_cf3c3748c3789bf4c2d252f8`，白苔舌象特征，PDF 页序 67 / 印刷页 51 / 页面文本块 3；原书截图 `output/e2e/book-page-67.png`。页面默认只显示原文和书名，点“查看出处”展开章节、页码、段落字段。正式段落编号尚未确认，显示“待核对”；文本块编号明确标注自动分段，未冒充正式段落号。

其余已核对来源在 PDF 页序 58、67、69、100。低置信 OCR 涉及的 57、64 页继续整页隔离；本轮未放行这些片段。审核内容变更或哈希不匹配时不进入用户报告。

## 实际通过的检查

- 开发者工具目录与本次构建一致；构建后清理编译缓存，确认运行中出现新版待复核区域。仅刷新模拟器曾继续显示旧代码，不能当作编译验收。
- `npm run typecheck`、`npm run build:mp-weixin` 通过。
- 后端 `pytest backend/tests -q`：47 passed，1 条已有 Starlette 弃用警告。首次受限临时目录运行失败，随后在正常本地环境重跑通过。
- Qwen 合约测试：3 passed（包括 report 模式）；未进行训练。
- 原图→中文标注→原图切换，框/标签说明；已保存框数与页面框数一致。
- 5 条合法、经来源核对的引用，点击展开页码；未发布低置信 OCR 页。
- 小程序历史列表重开当前报告，显示报告 ID 一致，内容与保存快照一致。
- 小程序导出按钮实际下载并调用文档打开流程，保存 PDF；另重复导出，两次正文与图片一致，报告内容未变化。
- PDF 原始嵌入照片与持久化照片逐像素一致；中文字体 SimHei 以 TrueType 子集嵌入。4 页逐页渲染核对，无中文乱码、框标签裁切。
- MySQL：报告用户、分析用户、图片所属用户一致；文件在持久化目录；原始症状、YOLO 结果与 Qwen 有效输出仍在库内。重启后端后，前一份报告也已重新打开并导出。

## 单次耗时（非性能基准）

| 阶段 | 秒 | 口径 |
|---|---:|---|
| YOLO | 0.272 | 后端检测 HTTP 调用 |
| BGE | 7.758 | 检索 HTTP 调用及审核过滤 |
| Qwen | 22.283 | 模型侧同步生成，1830 输入 / 267 输出 token |
| 后端分析总计 | 30.461 | 分析处理，不含前端交互 |
| 提交→报告可读 | 34.322 | 含上传、任务排队及查询 |
| PDF 渲染 | 0.048 / 0.042 | 两次重复导出的服务端渲染 |
| PDF HTTP 完成 | 0.070 / 0.066 | 同两次本地请求 |
| 小程序导出按钮→文件 | 3.617 | 含自动化调用开销 |
| 整条 UI 链路 | 141.262 | 选图→输入→生成→切图/截图→出处→历史→PDF，包含截图与自动化等待 |

完整原始计时位于 `output/e2e/timings.json`。这些计时来自一次执行，不能推断稳定延迟或医学质量。调试中曾遇 Qwen 不合法 JSON，已调整参数且拒绝发布失败结果；最后两份实际报告输出合法，未伪造替代生成内容。

## 截图与导出文件

- `output/e2e/upload-symptoms.jpg`：上传及输入。
- `output/e2e/report-annotated.jpg`：白苔中文框与点击后的解释。
- `output/e2e/report-original.jpg`：切回原图。
- `output/e2e/report-analysis.jpg`：检测特征、症状摘要、待复核区。
- `output/e2e/evidence-book-text.jpg`、`evidence-location.jpg`：原文书名与展开后的出处。
- `output/e2e/history.jpg`：实际历史列表。
- `output/pdf/real-e2e/report.pdf`：验收 PDF；`page-1.png` 到 `page-4.png` 为逐页渲染截图。
- `output/e2e/report.json`、`evidence.json`：本次快照；`report-repeat.pdf`：重复导出。

## 启动与复现

以下从项目根目录执行，各服务在单独终端运行；已启动的端口不要重复启动。数据库及模型均沿用已有配置和文件，不重建表，不重建索引。

```powershell
Set-Location F:\code\tongue-analysis\tongue-analysis
# 终端 1：复用现有本地 BGE/Neo4j 配置
powershell -NoProfile -ExecutionPolicy Bypass -File research\retrieval\real.ps1 -Action Serve
# 终端 2：默认 clean_v1；不传 UseV2
powershell -NoProfile -ExecutionPolicy Bypass -File research\multimodal\start.ps1 -Port 8002
# 终端 3：现有 FastAPI
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --no-access-log
# 终端 4：有前端改动时重新构建
Set-Location miniapp
npm run build:mp-weixin
```

开发者工具导入 `F:\code\tongue-analysis\tongue-analysis\miniapp\dist\build\mp-weixin`。构建后如仍显示旧页面，清理编译缓存再编译；保留业务存储。

真机待验证：手机与电脑在同一局域网，前端地址应为电脑局域网 IP，不能用手机自己的 127.0.0.1；保持符合当前微信调试域名要求。用自己的微信账号登录→舌象分析→相册或拍照→填写症状和持续时间→开始分析→查看报告→查看标注→点白苔框/标签→查看原图→查看知识依据→查看出处→我的→历史记录→打开同一报告→导出报告。预期检测、特征栏、历史及 PDF 一致，重复导出不会重新推理。开发联调账号的报告不会自动出现在微信账号历史里。

未验收：现场拍摄、手机触摸命中/缩放/横竖屏、微信真机登录及 PDF 分享、不同舌照上的泛化或临床质量。脚本已在完成时恢复选择器 mock、文档钩子与原登录状态；最后追加状态读取时项目窗口已不可连接，未因此重做已经通过的链路。
