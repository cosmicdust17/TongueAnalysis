# 第一阶段舌象图片检测

更新：已生成独立7类清洗副本 `datasets/clean_v1` 并通过复审。新子集的统计、隔离规则和训练命令见 [clean_v1交付](results/clean_v1/README.md)。下文21类原始数据的阻断结论继续有效，不适用于已隔离问题的新子集。

实际工程在 `F:\code\tongue-analysis\tongue-analysis`。使用Ultralytics YOLO11n官方预训练权重微调。本次只新增research实现，没有改动后端、mock、数据库、model-service或原始数据。项目及父级未找到AGENTS.md。

## 数据结论与修正方案

仅扫描TXT版本，没有合并COCO/XML图片。train/val/test为5594/572/553张，共6719张。完整输出：`results/data_audit/report.md`、`audit.json`、`manifest.json`、`class_counts.csv`及`visualizations/`。

**正式训练暂停，脚本会阻止启动。**

- TXT没有classes.txt；COCO三份本地表均为21类。train的19/20号为xinfeitu/xinfeiao，val/test为xinfeiao/xinfeitu。TXT自带YAML仍为20类，18/19号也与21类表不同，不能沿用。原始标签只出现0～19，没有20号，14/16/18号很少；不能自动推断编号含义。
- 133组像素完全相同的图片涉及278张，其中79组跨集合，涉及168张。133组的解析标注数值均不完全相等，不能直接称为已确认的标注冲突；其中exact_124仅表现为1像素以内数值差异候选。复核证据见results/data_review/review.md。字节哈希和像素哈希组有重叠，不得相加。
- 所有图片可解码；没有缺失标签、空标签、孤立标签；没有非法ID、非有限值、坐标范围错误或框越界。
- `train/images/D (427).jpg` 对应标签第5行重复；20张图片带EXIF旋转信息，需要确认标注坐标方向，不能直接旋转图片而不变换框。
- 未找到可确认的患者ID，A/B/C及数字文件名不能当作患者ID。只能声称检查精确重复，不能声称患者独立或排除近似重复。

CSV按原始ID统计成功解析且不重复的标注行，包括EXIF待核实图片，错误行不计。名称列和框图使用第一份候选表，19/20号名称未经确认；JSON保存全部类别表。名称原样保留，不自行翻译拼音医学含义。

修正方案：向提供者确认TXT真实类别顺序；逐组审核同图差异、重复行及EXIF方向；在research新建修正版，不覆盖原数据；同图、近似图和确认患者分组后重新划分并冻结测试集。重新检查修正版后才能正式训练。

用户已授权**仅冒烟**采用train/classes.txt顺序。冒烟排除所有重复组成员、错误图片及含19/20号标注的图片；seed=42，原train取32张、val取16张，完全不用test，仍保留21类头。冒烟只验证技术链路，不解决数据语义，也不能代表识别效果。

## 已执行的冒烟结果（2026-11-18）

1轮GPU训练成功，32张训练/16张验证，验证含49个框；batch=4没有调整，训练日志GPU_mem约1.17GiB。成功加载预训练参数448/499项并替换为21类检测头。输出目录为 `results/smoke/yolo11n-seed42`，best.pt和last.pt均已保存，含实际参数、类表、来源、依赖与曲线。

独立验证 `results/evaluation/smoke-val/metrics.json`：Precision=0、Recall=0、mAP50=0、mAP50-95=0。21类逐类输出完整，缺少真值的类别为null。单图 `A (349).jpg` 在conf=0.25下检测0个框，JSON及图片保存于 `results/smoke-prediction`。这是一轮小样本链路检查，不能用来宣称模型效果。未执行正式训练或测试集评估。

数据抽样共64张框图。两个合成用例覆盖非法标签、重复/越界/非有限坐标、跨集合重复、缺失标签与正式准备阻断；已通过。pip check通过。所有依赖已固定于 `requirements-lock.txt`；具体环境记录在实验目录environment.json。

## 环境与存储

独立环境：`research/.venv`，不复用后端环境。Python3.12.7、驱动560.94、RTX4060 Laptop约8GiB。PyTorch2.6.0+cu124、torchvision0.21.0+cu124，CUDA计算检查通过。选择CUDA12.4轮子，而不是把nvidia-smi的12.6当作安装要求。

官方依据：[PyTorch安装表](https://pytorch.org/get-started/previous-versions/)、[CUDA12.4驱动要求](https://docs.nvidia.com/cuda/archive/12.4.0/cuda-toolkit-release-notes/index.html)、[Ultralytics训练参数](https://docs.ultralytics.com/modes/train/)。560.94高于CUDA12.4 Windows最低551.61。每次运行保存实际全量依赖及环境信息。

```powershell
cd F:\code\tongue-analysis\tongue-analysis
. .\research\use-e-storage.ps1
# 缓存 E:\CodexData\cache\tongue-analysis\pip
# 临时文件 E:\CodexData\cache\tongue-analysis\temp
# 已安装环境仍在 F盘research/.venv；已有环境跳过下面三步
python -m venv research\.venv
.\research\.venv\Scripts\python.exe -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
.\research\.venv\Scripts\python.exe -m pip install -r research\requirements.txt
```

新终端先执行use-e-storage.ps1，作用域仅当前终端，不改系统环境。旧默认pip缓存迁往 `E:\CodexData\cache\tongue-analysis\previous-default-pip-cache` 保留，没有清空其他应用临时目录。

官方权重 `research/weights/yolo11n.pt` 来自 `https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt`。训练记录其SHA256。

## 数据检查与冒烟命令

```powershell
cd F:\code\tongue-analysis\tongue-analysis
. .\research\use-e-storage.ps1
.\research\.venv\Scripts\python.exe research\training\audit_data.py
# 有患者资料时加 --patient-csv 文件.csv，列为image_relative_path,patient_id
# 图片路径相对TXT根目录
.\research\.venv\Scripts\python.exe -m unittest discover -s research\training -p test_audit.py
.\research\.venv\Scripts\python.exe research\training\prepare_data.py --smoke --classes 'E:\软件工程概论\DataSet\TWC-Tongue\shezhen_datasets1\shezhen datasets\shezhenv3-coco\shezhenv3-coco\train\classes.txt'
.\research\.venv\Scripts\python.exe research\training\train.py --smoke --data research\configs\tongue21-smoke.yaml --name yolo11n-seed42
.\research\.venv\Scripts\python.exe research\evaluation\evaluate.py --weights research\results\smoke\yolo11n-seed42\weights\best.pt --data research\configs\tongue21-smoke.yaml --name smoke-val
.\research\.venv\Scripts\python.exe research\evaluation\predict.py --weights research\results\smoke\yolo11n-seed42\weights\best.pt --image 'research\datasets\smoke\val\images\A (349).jpg' --output research\results\smoke-prediction
```

数据副本及配置拒绝覆盖；重复实验使用新name/output。YOLO标签缓存仅写research副本。imgsz=640、batch=4、workers=0、seed=42；显存不足减半batch并记录。CUDA不可用直接停止，不跑长时间CPU训练。AMP关闭，避免自动下载其他模型做AMP检查。

## 正式训练、评估、单图预测

**数据问题解决后由用户执行。** 在 `research/datasets/reviewed` 放独立修正版TXT目录（名称含txt，含train/val/test的images/labels）和唯一确认后的classes.txt，不能混入原始冲突表：

```powershell
cd F:\code\tongue-analysis\tongue-analysis
. .\research\use-e-storage.ps1
.\research\.venv\Scripts\python.exe research\training\audit_data.py --source research\datasets\reviewed --output research\results\reviewed_audit
.\research\.venv\Scripts\python.exe research\training\prepare_data.py --audit research\results\reviewed_audit
# 自动读取21类生成tongue21.yaml；有阻断项则拒绝生成
.\research\.venv\Scripts\python.exe research\training\train.py --data research\configs\tongue21.yaml --epochs 100 --batch 4 --name yolo11n-seed42
.\research\.venv\Scripts\python.exe research\evaluation\evaluate.py --weights research\results\formal\yolo11n-seed42\weights\best.pt --data research\configs\tongue21.yaml --split val --name formal-val
# 模型、参数及阈值固定后，才使用测试集
.\research\.venv\Scripts\python.exe research\evaluation\evaluate.py --weights research\results\formal\yolo11n-seed42\weights\best.pt --data research\configs\tongue21.yaml --split test --final-test --name final-test
.\research\.venv\Scripts\python.exe research\evaluation\predict.py --weights research\results\formal\yolo11n-seed42\weights\best.pt --image 'F:\your-images\tongue.jpg' --conf 0.25 --output research\results\single-image
```

默认100轮、patience=20。训练保存best.pt、last.pt、args.yaml、results.csv、曲线、训练/验证框图、依赖、类别映射、数据来源和实际参数。评估metrics.json保存Precision、Recall、mAP50、mAP50-95及21类指标；不存在于该评估集的类别指标为null。冒烟只有一个曲线数据点，分数不能用于效果结论。

## 未来系统接入

现有model-service的POST /v1/infer接收image和必填symptoms，predictor尚未实现，health.ready=false。未来独立环境加载正式权重和类别表，复用单图流程；本阶段忽略症状，不宣称融合。

现有ModelResult顶层禁止额外字段，不能直接返回检测JSON。未来适配器可用tongue_features表达原始类别及分数，完整检测结构放fusion_result.image_detection（需确认下游约定），或另建版本化检测接口；不生成疾病、融合summary或query_terms。本次保持服务与mock不变。

prediction.json保留class_id、class_name、model_score、box_xyxy_pixels、图像尺寸、阈值、权重SHA256模型版本；by_class聚合数量、最高分及全部检测框。分数不是医学概率。空检测如实输出空列表；另存prediction.jpg。
