# YOLO11n 内部联调

实际项目根目录：`F:\code\tongue-analysis\tongue-analysis`。未找到适用的 AGENTS.md。

## 当前配置与实现

- 权重：`research/results/formal/clean-v1-yolo11n-seed42/weights/best.pt`。
- 权重 SHA256：`4455a8217b44db4f63da7d52c593698528f310c4269a12a9c429d32fdc88f5a6`。
- 模型版本：`clean-v1-yolo11n-seed42-4455a8217b44`。
- 推理参数固定为 `imgsz=640`、`conf=0.218`；当前使用 CPU，未训练或修改权重。
- 校验权重的 7 类顺序：红舌、紫舌、裂纹、齿痕、白苔、黄苔、黑苔。
- 复用后端 `HttpAdapter` 和 `/v1/infer` 协议。后端有效配置仍为外层 `F:\code\tongue-analysis\.env`，本次将 `MODEL_PROVIDER` 改为 `http`，`MODEL_BASE_URL` 改为 `http://127.0.0.1:8001`。
- 知识检索保持关闭，未依赖 Neo4j。症状照常入库和显示，不宣称 YOLO 使用了症状进行多模态推理。

`model-service/predictor.py` 加载并校验模型，执行真实推理。每个检出类别以最高实际检出分数展示特征，所有框、类别和分数保存在 `analyses.result.fusion_result.detections`；同时保存完整权重哈希及推理参数。
没有裂纹框时，特征为 **“未检出裂纹特征”**，置信度为空，不生成虚构框或概率。
报告注明内部联调、未检出不代表不存在、分数不是医学概率。

修改文件还包括 `model-service/app.py`、`model-service/requirements.txt`、报告生成器、登录页开发入口说明及报告页模型版本显示。
新增 `backend/tests/test_detector.py`、`scripts/verify_yolo.py`，并调整原有“模型未连接”测试显式使用缺失权重。

## 实际通过的检查

1. 后端回归和检出映射测试：**36 项通过**，包括有/无裂纹框分支及真实结果协议校验。测试仍隔离真实数据库。
2. 小程序 `npm run typecheck`、`npm run build:mp-weixin`。
3. 真实权重成功加载，服务就绪；实拍图通过业务上传接口进入 HTTP 模型服务，真实推理返回 `is_demo=false`。
4. MySQL 保存图片稳定路径、症状、分析结果、报告内容和模型版本；报告接口、历史重新读取、原图读取、PDF 导出通过。
5. 这张实拍图检出 1 个框，**没有裂纹框**，报告特征实际包含“未检出裂纹特征”。本检查不评价模型识别是否准确。

实际记录：`storage/yolo-integration-check.json`。
报告 ID：`f1b639e8-922f-4e7c-a645-ea7faa02781b`。
验证使用现有上传目录中的实拍图，不是合成图片；报告属于“开发联调入口 → 用户端”账号，不自动合并到微信账号。

复现接口验证（会新增一份内部联调报告）：

```powershell
cd F:\code\tongue-analysis\tongue-analysis
.\.venv\Scripts\python.exe scripts\verify_yolo.py --image storage\uploads\4809160ad7274c03ae3931dd21f29c9a.jpg
```

## 手动启动

两个服务当前已在后台启动；以下命令用于以后停止服务后的重启，不要在端口已占用时重复启动。

推理服务使用现有训练环境中的 PyTorch 和 Ultralytics，以及本次安装的 HTTP 服务依赖：

```powershell
cd F:\code\tongue-analysis\tongue-analysis\model-service
..\research\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001 --workers 1
```

另一个终端启动业务后端：

```powershell
cd F:\code\tongue-analysis\tongue-analysis\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

不带额外环境变量时使用上述默认权重与 CPU。`MODEL_WEIGHTS` 可以指定权重路径，加载时仍要求相同的 7 类映射。
可选 `MODEL_DEVICE` 遵循已安装 Ultralytics 的设备选择；本次没有切换 GPU 或调整推理阈值。
如果配置 `MODEL_API_KEY`，模型服务和后端从相同有效配置读取，不将密钥发到小程序。

## 待开发者工具/真机验证

本次没有可用的小程序界面控制接口，因此以下交互与视觉结果未宣称实测：

1. 重新打开已编译工程 `miniapp/dist/build/mp-weixin`，点击“编译”。电脑模拟器本地调试关闭域名校验。
2. 登录后上传一张自己的实拍照片、填写症状和持续时间、提交分析。预期完成后打开报告，显示真实模型版本与“内部联调模型输出”，新报告不显示“模拟演示数据”。旧 mock 报告保留原标记。
3. 当原始结果没有裂纹检出框时，预期显示“未检出裂纹特征”；有框时显示“检出裂纹特征”。不应解释为“没有裂纹”。
4. 返回“我的 → 历史记录”，重新打开新报告，核对图片关联、症状、特征与模型版本；退出后使用同一账号重登，再次确认可打开。
5. 开发联调账号可查看上面的现有验证报告；真实微信账号需要自行生成新报告，不会合并开发账号历史。
6. 手机真机上 `127.0.0.1` 指向手机自身：把 `miniapp/.env` 的 `VITE_API_BASE_URL` 改为电脑可访问的局域网 IP 后重新构建，电脑和手机处于可互通网络，确保 8000 端口可达。8001 仅需供本机业务后端访问。

训练、模型效果评估及真机交互不属于本次已通过的检查。
