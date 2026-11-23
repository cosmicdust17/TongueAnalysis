# 模型接入约定

当前已通过现有 HTTP 协议接通 7 类 YOLO11n；实际权重、参数、启动命令与已验证范围见 [内部联调记录](yolo-integration.md)。下文保留通用接口约定。

后端调用边界在 `backend/app/integrations/inference/base.py`，公开签名：

```python
async def analyze(image_path: str, symptoms: str) -> ModelResult: ...
```

用户上传图像在业务后端校验并转换为JPEG，保留方向，清除原始EXIF，最长边缩至2048。你的训练/推理预处理需要进一步进行训练所需的缩放、归一化、裁剪和分词，并保持一致。若模型需要原始分辨率，应同步调整上传归一化策略。

独立服务使用 `POST /v1/infer`，请求为 `multipart/form-data`：

| 字段 | 类型 | 含义 |
|---|---|---|
| image | 文件 | JPEG舌象图像 |
| symptoms | 文本 | 用户症状，最多200字 |

返回JSON样例（这里只是接口示例，非真实预测）：

```json
{
  "schema_version": "1.0",
  "model_version": "your-model-version",
  "is_demo": false,
  "tongue_features": [
    {"name": "舌色", "value": "你的实际类别标签", "confidence": 0.85}
  ],
  "fusion_result": {
    "summary": "你的模型真实返回的融合表征说明",
    "query_terms": ["用于匹配图谱的实际术语"]
  }
}
```

`confidence` 可为null；不能填入随意编造的概率。真实模型明确返回 `is_demo=false`，测试服务则返回true。即使模型返回false，只要证据引用了示例资料，最终报告仍会标为演示数据。

`fusion_result` 保存于分析任务原始结果，不直接作为面向用户的诊断文本展示。图谱检索读取其中的query_terms，同时结合舌象标签与症状词项。标签与图谱命名不同时，可在图谱别名中维护对应关系。

服务还需提供 `GET /health`，返回 `{"ready":true,"schema_version":"1.0"}`。尚未加载模型时ready应为false，推理接口返回503。若设置MODEL_API_KEY，两个接口均使用 `Authorization: Bearer ...`。

接入步骤：

1. 在 `model-service/predictor.py` 实现load与analyze，添加实际模型依赖。
2. 加载训练权重、标签映射、模型配置、图像预处理参数、文本分词器；在load完成后才报告ready。
3. 使用独立Python环境启动：`uvicorn app:app --host 0.0.0.0 --port 8001`（model-service目录）。
4. 后端设置MODEL_PROVIDER=http、MODEL_BASE_URL与可选API密钥，重启后端。
5. 使用 `scripts/verify_stack.py` 和你自己的已标注样本验证接口；脚本上传的是合成图片，只验证系统连通，不能替代模型效果评估。

当前检索基线在 `backend/app/integrations/retrieval/retriever.py`。实体按名称/别名精确词项匹配，最多扩展两跳，只允许有来源的已发布实体和关系进入证据，按词项长度和扩展衰减分数排序。该分数是排序权重，不是医学概率。后续可替换实体匹配、向量召回或重排序函数。

报告由 `backend/app/integrations/generation/generator.py` 的确定性模板组织。未检索到依据时明确标记insufficient，不产生进一步判断。证据快照包含实体内容、出处、关联路径及路径来源；图谱之后的修改不会改写历史报告依据。
