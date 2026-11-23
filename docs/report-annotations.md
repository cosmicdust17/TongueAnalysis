# 报告标注与 PDF 验收

## 交付行为

实际项目为 `F:\code\tongue-analysis\tongue-analysis`。本次检查未找到适用的 AGENTS.md。
继续使用已有报告、MySQL、HTTP 模型及 PDF 导出流程。

默认模型明确配置为 clean_v1。用户提供的本轮统计为：clean_v1、clean_v2 裂纹检出均为 29/83，误报分别为 29、36；本次没有重跑这 83 张评估，不将该统计写成系统自动验证结果。
clean_v2 保留为实验权重，可通过下列命令选择，再重启模型服务：

```powershell
cd F:\code\tongue-analysis\tongue-analysis
.\.venv\Scripts\python.exe scripts\select_detection_model.py clean_v2
# 验收结束后恢复默认
.\.venv\Scripts\python.exe scripts\select_detection_model.py clean_v1
```

模型服务启动命令：

```powershell
cd F:\code\tongue-analysis\tongue-analysis\model-service
..\research\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001 --workers 1
```

命令仅修改根目录 `.env` 的权重和类别 YAML 路径；服务已经运行时先停止原模型进程再启动。当前有效配置及运行实例已恢复为 clean_v1。

## 结果快照与中文说明

- 每次生成报告，将本次模型版本、权重哈希、图片宽高、归一化 xyxy 框、实际检出分数、中文名称、颜色及观察说明存入 `reports.content.annotations`。
- 原始检测结果继续存于 `analyses.result`。报告页面和 PDF 使用已保存的 annotations，不使用当前默认模型重推理。
- 历史报告若尚未保存 annotations，会从当时的原始分析结果和原图补存一次快照；没有保存检测框的旧报告明确提示不可复现，不重推理或伪造框。
- 权重类别名称转换集中在 `shared/tongue_features.json`；模型按加载权重的 class_name 映射，不假设任意权重都使用同一 class_id 顺序。页面、PDF 均读取同一报告快照中的中文名称与说明。
- 观察说明只解释颜色、纹理和轮廓，不是教材引文。已有教材证据仍使用生成时保存的原文及书名/来源字段，本次没有新增或虚构教材引用。
- 无框时统一显示“本次未检出可标注的舌象特征”。未检出裂纹特征的原提示继续保留。

## 页面与 PDF

报告页面的舌照旁增加“查看标注”和“放大查看”；点击框、中文标签或类别标签显示简短说明。同类框合并为一个类别入口。
图片使用 aspectFit，框按图片实际缩放比及水平/垂直留白换算；全屏及缩放时，图片与框放在同一 movable-view 中共同变换。报告页启用自动方向，并在窗口改变、图片加载及全屏切换时重新测量。
接近的标签错位排列，避免覆盖。

PDF 嵌入原始已上传 JPEG，直接绘制矢量框与中文标签，不截取屏幕低分辨率图；图下按类别合并观察说明。使用本机黑体 TrueType 字体嵌入 PDF，标签限制在图片边界内。已保留原有知识依据和报告主体。

## 实际通过的检查

- 后端完整回归：43 项通过；最终相关回归 5 项通过。只有已有测试客户端依赖弃用提示。
- 小程序类型检查和微信构建通过。
- 有框、无框、真实竖版图均调用真实 clean_v1 完成上传、推理、报告保存、历史重开及 PDF 导出。
- 横屏/竖屏容器、aspectFit 留白及 1/2/4 倍共同缩放的几何检查通过，重叠标签错位检查通过。
- 三类页面在开发者工具中触发真实绑定的 tap 事件处理器，验证原图/标注切换、框与标签说明、全屏及 2 倍缩放。截图已逐一查看。由于工具选择器不支持进入自定义组件内部，这部分是实际事件处理器和渲染验证，不是手指点击命中测试。
- 三份 PDF 均经 Poppler 渲染检查：中文正常、图片与框对齐，标签可见；TrueType 已嵌入，原图像素分别保留为 441×445、640×400、776×1296。
- 实际将服务切换为 `clean-v2-yolo11n-seed42-d0db4a1998a4` 后，重开以下三份历史报告、重新导出 PDF：快照与原保存值一致，版本仍为 clean_v1；然后恢复 clean_v1。
- 模拟器验收临时切换至开发验收用户，结束后已恢复原用户；未合并用户历史。

| 样例 | 来源 | 框数 | 报告 ID |
|---|---|---:|---|
| 有框 | 已有上传目录实拍图 | 1 | c16a33df-9826-432a-be55-b92c419108c5 |
| 无框 | 固定种子噪声测试图，非舌照 | 0 | 442649f5-31bf-43a4-9d78-73023f6b2070 |
| 竖版 | clean_v1 验证集中的真实竖版照片 | 2 | 56364d68-5293-4d4a-abd3-f563e8a46c5b |

纯灰图片被模型检出了框，因此使用固定种子噪声图验证无框界面；没有抬高阈值或清除真实推理输出。本次验证报告展示与持久化，不评价临床识别效果。

样例文件位于 `output/pdf/annotation-check/`：`boxed.pdf`、`empty.pdf`、`portrait.pdf`，对应页面截图为 `*-ui.jpg`，放大截图为 `*-zoom.jpg`，归一化快照为 `reports.json`。

复现检查：

```powershell
cd F:\code\tongue-analysis\tongue-analysis
.\.venv\Scripts\python.exe -m pytest -q backend/tests --tb=short
node scripts\check_annotation_geometry.cjs
.\.venv\Scripts\python.exe scripts\verify_annotation_reports.py
# 切换至 clean_v2 并重启模型后，可执行历史复现检查
.\.venv\Scripts\python.exe scripts\verify_model_history.py
```

## 待真机确认

在实际手机上使用同一账号进入报告 → 查看标注 → 点击框/标签 → 放大，验证触摸命中；旋转横竖屏及双指缩放、拖动，检查边框始终贴合原图。数学变换和模拟器事件已验证，真实手机旋转和多指手势未实测。
如使用开发验收样例，登录“开发联调入口 → 用户端”查看带“标注验收”症状的历史记录；普通微信账号的历史不会自动合并这些样例。

## 主要修改文件

`shared/tongue_features.json`、`model-service/predictor.py` 与 `app.py`、`backend/app/services/annotations.py`、`analysis_service.py`、`export_service.py`、`backend/app/api/reports.py`、`miniapp/src/components/AnnotatedPhoto.vue`、报告页、类型定义、坐标工具、报告页方向配置，以及相关测试与验收脚本。Docker 构建同步复制共享映射。
