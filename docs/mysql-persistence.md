# MySQL 持久化

本机有效代码在 `F:\code\tongue-analysis\tongue-analysis`，外层同名目录多为早期空文件，未覆盖这些文件。
未找到适用于此工作区的 `AGENTS.md`。

## 配置

真实连接保存在 **`F:\code\tongue-analysis\.env`**，优先于内层 `.env`；进程环境变量的优先级最高。
密码含 `@`、`:`、`/`、`#` 等字符时，必须在连接 URL 中百分号编码。

```dotenv
DATABASE_URL=mysql+pymysql://账号:编码后的密码@127.0.0.1:3306/tongue_analysis?charset=utf8mb4
KNOWLEDGE_RETRIEVAL_ENABLED=false
MODEL_PROVIDER=mock
AUTO_CREATE_SCHEMA=false
STORAGE_PATH=F:/code/tongue-analysis/tongue-analysis/storage
```

保留现有 JWT_SECRET、APP_ENV 等配置。此配置关闭知识检索、知识管理接口与图谱服务探测；
不连接 Neo4j，也不生成示例依据。报告 JSON 中 `evidence_status=disabled`，报告正文与 PDF 注明“知识检索尚未启用”。
HTTP 模型适配器保持不变，mock 结果及报告仍带模拟标记和模型版本。

## 初始化与启动（PowerShell）

```powershell
cd F:\code\tongue-analysis\tongue-analysis
.\.venv\Scripts\python.exe scripts\init_mysql.py
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

`init_mysql.py` 先核对 `sql/01_schema.sql` 和 ORM 的建表定义，再检查真实 MySQL：

- 空库才执行 `alembic upgrade head`。
- 已有完整表且字段、类型、可空性、主键、唯一约束、索引、外键一致，才执行 `alembic stamp head`。
- 已有版本则保持版本并检查；部分建表、未知版本或结构不符时停止，不删除或覆盖数据。

本次实库已有业务表，结构一致，实际执行的是 `stamp head`，版本为 `0001`，未重复建表。

## 持久化与验证

保留现有上传与数据库实现：上传图片经校验、归一化后保存到持久化目录，
`stored_files.path` 是服务器绝对路径，关联 `owner_id`；数据库记录不使用微信临时文件路径。
分析保存症状、持续时间、图片 ID、状态、进度及模型原始结果；报告保存完整 JSON、用户 ID、任务 ID、模拟标记。
模型版本位于报告 JSON 中。历史、详情、图片与 PDF 均校验所属用户。

```powershell
cd F:\code\tongue-analysis\tongue-analysis
.\.venv\Scripts\python.exe scripts\verify_persistence.py --mysql --port 8003
```

该验证会创建两个独立测试用户、一张合成图片及一份标注为模拟的报告；保留 MySQL 测试记录便于核对。
会启动并彻底停止专用测试服务，确认旧服务不可访问后再用新进程启动，不占用 8000 端口的日常服务。
不删除已有表、不使用真实舌象图片、不训练模型。

2026-11-18 实际验证通过：上传 → 提交分析 → mock 报告 → 历史查询 → PDF 导出；
重启后图片内容哈希、症状、持续时间、任务结果与完整报告一致；其他用户读取图片、任务、详情、依据、PDF 返回 404，历史为空。
报告 ID：`176f91c4-08c3-4ade-bf00-d28d7028b599`。

已有 pytest 套件新增了关闭检索与 SQL 一致性检查；测试依赖安装未获允许，未运行完整 pytest 套件。
上述实际 MySQL HTTP 与进程重启检查已独立运行并通过。
