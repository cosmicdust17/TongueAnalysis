# Windows 实测记录 — 2026-11-19

项目和父目录未发现 AGENTS.md。沿用现有 FastAPI HTTP 适配器，默认 YOLO clean-v1、mock/http 开关与 0.218 固定阈值均保留。实验文件和独立环境位于 research/multimodal，缓存位于 E:\CodexData\cache\tongue-analysis。

硬件：RTX 4060 Laptop，8188 MiB；驱动 560.94。Python 3.12.7，torch 2.6.0+cu124，Transformers 4.57.1，PEFT 0.17.1，bitsandbytes 0.48.2。完整依赖见 results/requirements-lock.txt，pip check 已通过。

官方基座 revision：`89644892e4d85e24eaac8bacfd4f463576704203`。
官方权重 SHA256 实际校验通过：`7de1838c87a5349b016c26a1c3f7d2bc400a3d485f95ef39a7059ffd734977a0`。

## 基线和真实 HTTP 上传

输入：clean_v2 原 val 中 A (1).jpg；联调用模拟症状“近一周口干，睡眠欠佳”。症状不是患者配对资料，结果不作为医学或实验效果证据。检测使用默认 clean-v1，YAML 类别核对通过。

| 项目 | 耗时 | 峰值 allocated MiB | 峰值 reserved MiB |
|---|---:|---:|---:|
| CLI 图文推理 | 9.518 秒 | 1720.53 | 2136 |
| FastAPI 实际 multipart 上传、GPU 推理、响应校验 | 7.973 秒 | 1720.53 | 2136 |
| QLoRA 两步训练（不含加载/保存） | 1.502 秒 | 2537.43 | 3348 |
| 适配器重新加载后 val 推理 | 4.350 秒 | 1578.43 | — |

CLI 全过程 88.929 秒，其中加载 76.891 秒，受远程 HEAD 的 SSL 重试影响；离线运行可设置 `$env:QWEN_OFFLINE='true'`。首次权重下载约 13 分钟，不能混入纯推理耗时。显存数字来自 PyTorch 当前进程统计，不是整卡占用。

实际可校验输出包括 `symptoms_summary="口干，睡眠欠佳"`、分析字符串、空 `cited_chunk_ids`。独立检索未运行，CLI 明确返回 `evidence_status="unavailable"`。检测字段单独保留：白苔 class_id=4，score=0.6260。完整输入、输出、框和指标见 results/baseline.json；真实上传响应见 results/http-smoke.json。

随后用可选 clean-v2 权重、同一 val 图片和模拟症状实际验证三种 FastAPI 输入，权重/YAML 核对通过；`http-smoke.json` 保存此次较新的三模式结果：

| clean-v2 联调模式 | 推理秒数 | 峰值 allocated MiB | 峰值 reserved MiB |
|---|---:|---:|---:|
| image | 10.485 | 1888.86 | 2136 |
| symptoms | 3.761 | 1592.03 | 2170 |
| both | 9.644 | 1892.38 | 2170 |

三种模式 JSON 均通过校验；症状模式的 Qwen 输入不包含图片或 YOLO 结果。此为接口消融冒烟，没有真实配对参考输出，不能用于三组模型效果比较。

Qwen 的图像描述出现“轻微裂纹”，YOLO 则未检出裂纹。系统保留两者独立输出，说明通用 2B 基座的视觉描述仍可能与检测冲突，需要配对病例和人工审核。JSON 合法不代表内容准确。

## 实际 QLoRA 冒烟

clean_v2 转换得到 train=3653、val=244；保持原划分，只输出已标注属性及未知属性，不构造阴性标签，不使用 test。冒烟上限4条训练样本，实际执行2步（使用前2条），batch=1，最大像素65536，文本/视觉合计长度上限1024，seed=42，LoRA rank=8，语言层 q/v、视觉冻结。

实际 loss：0.501590、0.202884；实际梯度范数：3.661494、1.078486，均为有限非零值。已执行 optimizer.step、保存 adapter、释放模型、重新加载4-bit官方基座与adapter、在val图像生成。全流程43.564秒，results/qlora-smoke/run.json 状态为 passed，适配器在同目录 adapter 中。

**passed 只代表流程冒烟通过。** 两步后的原始输出包含多种未经验证的属性，而且遗漏部分未知类别，不能当作已训练合格模型。已保留完整原文；未报告准确率，未启用它替换默认模型。正式训练仍需更多步数与独立验证。

## 遇到并处理的问题

- Windows 受限临时目录的文件替换让已有测试失败；在正常临时目录重跑通过，没有修改业务代码去绕开。
- 首轮处理器使用字符串 content 导致 TypeError；统一改为多模态内容列表，图文和训练均已实际重跑。
- 首轮基线忽略症状摘要；调整提示，增加空摘要拒绝校验，再运行通过。
- 训练检查点警告提示冻结视觉输入无梯度；改为 use_reentrant=False，并检查实际 LoRA 梯度非零后重跑通过。
- 下载/HEAD 请求曾长时间停顿及 SSL EOF 重试。官方权重最终完整到本地并校验，保留可断点的官方分段下载脚本；本次无需分段重新下载。离线选项避免日常推理反复探测网络。
- 知识服务当前代码的 tongue_features 是文本，location 是对象；本后端请求/响应已对齐，并保留 is_demo 标记。未修改知识服务实现。

## 尚缺数据和验证范围

缺少同病例舌照、真实症状、审核参考摘要/分析、必要背景与患者分组，以及对应证据ID/教材溯源。真正图文联合训练和三组同病例效果评估入口已写好，但不能用检测标注或模拟症状替代这些数据，因此没有执行或编造联合训练和效果评估结论。

主应用适配器、原文回填、未知引用ID拒绝、检索断线、报告字段和既有流程经回归测试；实际 GPU 模型已通过 FastAPI 上传边界。没有使用真实微信账号发起线上全流程，也未更改运行中服务或生产数据库。

最终回归：`47 passed, 1 warning`（9.49 秒）；警告为现有 Starlette/httpx 迁移提示。运行命令见 README。
