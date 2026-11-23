# Qwen3-VL 本地实验与小程序后端接入

工作目录：`F:\code\tongue-analysis\tongue-analysis`。本目录独立 `.venv`，不修改原后端/YOLO 环境。所有新增依赖、HF、Torch 缓存与临时目录沿用 `E:\CodexData\cache\tongue-analysis`。官方模型为 [Qwen/Qwen3-VL-2B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct)，Transformers 4.57.1 + CUDA 12.4 PyTorch 2.6 + NF4 双重量化，原生 Windows，不要求 FlashAttention。

## 安装及单次推理

```powershell
Set-Location F:\code\tongue-analysis\tongue-analysis
.\research\multimodal\setup.ps1
. .\research\multimodal\use-env.ps1
$py = '.\research\multimodal\.venv\Scripts\python.exe'
& $py research/multimodal/prepare_data.py
$sample = Get-Content research/multimodal/data/recognition/val.jsonl -First 1 | ConvertFrom-Json
$env:MODEL_DATA_YAML = (Resolve-Path research/datasets/clean_v2/data.yaml).Path
& $py research/multimodal/infer.py --image $sample.image --symptoms '近一周口干，睡眠欠佳' --mode both --retrieval-url http://127.0.0.1:8010 --output research/multimodal/results/baseline.json
# 消融：同一病例分别使用 image / symptoms / both。
& $py research/multimodal/infer.py --image $sample.image --mode image --output research/multimodal/results/image.json
& $py research/multimodal/infer.py --symptoms '近一周口干，睡眠欠佳' --mode symptoms --output research/multimodal/results/symptoms.json
```

上例症状是联调模拟输入，不是图片所属患者的真实症状，不能用于效果评估。默认 YOLO 权重仍是 clean-v1，阈值 0.218、图像尺寸 640 不变。若要联调 v2，在当前终端设置：

```powershell
$env:MODEL_WEIGHTS = (Resolve-Path research/results/formal/clean-v2-yolo11n-seed42/weights/best.pt).Path
$env:MODEL_DATA_YAML = (Resolve-Path research/datasets/clean_v2/data.yaml).Path
```

运行时核对权重 names 和 YAML names。0–6 分别为 hongshe、zishe、liewenshe、chihenshe、baitaishe、huangtaishe、heitaishe。输出保留权重 SHA256 和真实 detections。v2 裂纹固定阈值召回持平、误报增加，因此不替换默认。

Qwen 的 JSON 严格限定 `symptoms_summary: str`、`analysis: str`、`cited_chunk_ids: list[str]`。非法 JSON、额外字段、未知证据 ID 均不作为成功报告。CLI 保存 `invalid_output` 和原始输出供排查，服务返回 502。记录推理秒数、输入/输出 token、PyTorch 峰值 allocated/reserved MiB；这是当前进程的张量/缓存占用，不能当作整卡占用。首次加载耗时另记。

## 模型服务和主应用

模型终端：

```powershell
.\research\multimodal\start.ps1 -Port 8002
# v2 是显式可选项：
.\research\multimodal\start.ps1 -UseV2 -Port 8002
```

主应用终端（保留已有数据库、鉴权和工作进程配置）：

```powershell
. .\research\multimodal\config.example.ps1
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --workers 1
```

`MODEL_PROVIDER=mock/http` 切换不变。仅 `MULTIMODAL_ENABLED=true` 使用两阶段 HTTP 适配器：上传至 `/v1/detect` → 后端检索 → 带证据上传至 `/v1/infer`。模型服务必须以 `MODEL_MODE=qwen` 启动（start.ps1 已设置）。关闭 MULTIMODAL_ENABLED 即恢复原 HTTP 检测流程。MODEL_API_KEY 沿用原配置，两端一致。

小程序继续走既有上传、创建 analysis、轮询、获取 report 接口，不需要更换业务路由。报告新增独立 `yolo_detections`、`inference_metrics`、`cited_chunk_ids` 和明确的 `evidence_status`，症状摘要和分析由 Qwen 生成。原文/出处仅从后端检索结果填入证据快照；不读取 Qwen 生成的出处。证据 chunk_id 保留在快照，数据库旧的 36 字符实体字段用确定性 UUID 映射兼容，无需迁移。

## 与独立知识检索服务约定

`RETRIEVAL_BASE_URL` 是根地址，后端调用 `POST /v1/retrieve`，请求：

```json
{"symptoms":"口干","tongue_features":"检出裂纹特征；检出白苔特征"}
```

响应（最多 10 条，chunk_id 唯一）：

```json
{"evidence":[{"chunk_id":"book:chapter:001","text":"服务返回的教材原文","source_title":"服务返回的教材名称","location":"章节/页码"}]}
```

`location` 也接受独立检索服务使用的对象（chapter、pdf_page、printed_page、paragraph）；完整保留在证据快照中。保留服务返回的 `is_demo` 标记。

状态：`disabled` 未配置/关闭，`unavailable` 连接失败、超时或响应不合法，`empty` 成功但无证据，`available` 有证据。不可用时仍运行图文推理；Qwen 无权引用任何 ID。响应中的原文、书名和位置来自独立服务，本项目不实现该服务。`available` 描述检索状态，最终引用数可以为零。

## 舌象属性 QLoRA 冒烟

```powershell
. .\research\multimodal\use-env.ps1
$py = '.\research\multimodal\.venv\Scripts\python.exe'
& $py research/multimodal/prepare_data.py
$env:QWEN_MAX_PIXELS = '65536'
& $py research/multimodal/train.py --task recognition --mode image --steps 2 --samples 4 --max-length 1024 --output research/multimodal/results/qlora-smoke
& $py research/multimodal/recognize.py --image $sample.image --adapter research/multimodal/results/qlora-smoke/adapter
```

固定 batch=1、LoRA rank=8，仅语言层 q/v，视觉层冻结、梯度检查点、BF16 计算。图像不做随机裁剪，避免丢失属性；不截断图像 token。长度超限会明确报错。按实测调像素和文本长度；不要并行启动占 GPU 的模型服务和训练。

转换仅读取 train/val，3653/244 条；不重划分、不用测试集训练或调参。目标为 `annotated_attributes` 和 `unknown_attributes`；缺失标注不是负标签。仅检测数据禁止训练 symptoms/both。训练保存 adapter，释放模型，重新加载官方 4-bit 基座和 adapter，对 val 图像实际生成，再写 `run.json`。`passed` 仅表示训练/保存/重载/生成流程完成，不代表少量训练步已获得识别准确率。失败文件含 stage、完成步数、完整 traceback 和可复现命令。

## 真正图文联合微调和三组消融

需要同病例舌照、真实症状及经审核的 JSON 参考输出。每行格式如下（此例仅解释结构，不是可评估病例）：

```json
{"case_id":"real-case-id","split":"train","image":"F:/data/case.jpg","symptoms":"真实同病例症状","reference_kind":"paired_case","is_simulated":false,"reference":{"symptoms_summary":"经审核症状摘要","analysis":"经审核分析","cited_chunk_ids":[]}}
```

train/val 分开文件，图片内容哈希不能重叠；病例应先按患者分组隔离。没有提供证据时 reference 引用必须为空。保持已有 test 隔离；此入口只接受 train/val，不接受模拟输入。

```powershell
& $py research/multimodal/train.py --task joint --mode both --train F:/data/paired-train.jsonl --val F:/data/paired-val.jsonl --steps 100 --output research/multimodal/results/joint
# 三组：官方基座、舌象 adapter、真正联合 adapter；每组同病例 image/symptoms/both。
& $py research/multimodal/evaluate.py --cases F:/data/paired-val.jsonl --recognition-adapter research/multimodal/results/qlora-smoke/adapter --joint-adapter research/multimodal/results/joint/adapter
```

评估不调用 YOLO 或检索，保证症状组没有图像/检测标签泄漏；输出逐病例 JSONL、同一 cohort SHA256、合法性、耗时、显存和描述性字符 bigram F1。文本重合不代表医学正确性，需要专家评价事实一致性与证据支撑。目前没有真实配对病例，不能给出三组效果结论，也不能声称完成联合训练。

## 检查与复现实测

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests research/multimodal/test_contracts.py -q
& $py -m pip freeze > research/multimodal/results/requirements-lock.txt
```

实测记录见 `VALIDATION.md` 和 results 下 JSON。缺少的数据：同患者症状、持续时间/必要背景、审核后的摘要和参考分析、参考证据 ID 与教材溯源、患者分组标识和真实配对验证病例。目前检测标签只能支持已标注舌象属性学习。

已下载后可设 `$env:QWEN_OFFLINE='true'` 避免联网探测。模型 revision 固定为 `89644892e4d85e24eaac8bacfd4f463576704203`，更换基座时同时配置 QWEN_MODEL/QWEN_REVISION。完整性校验或网络停顿时可运行 `& $py research/multimodal/download_weights.py`，仅下载同一官方文件并核对 SHA256；分段缓存也位于 E 盘。
