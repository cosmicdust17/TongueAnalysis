# 舌象智能分析系统

uni-app + Vue 3 + TypeScript + Pinia 小程序，FastAPI + SQLAlchemy + Alembic 后端。MySQL 保存业务记录；Neo4j 保存知识图谱。训练模型由独立 HTTP 接口接入，当前默认返回明确标注的固定模拟结果。

仓库包含小程序、后端、模型与检索服务源码，以及数据库迁移和本地部署脚本。请根据 `.env.example` 和 `miniapp/.env.example` 配置本机环境。启用真实推理和教材检索时，需要另行准备模型权重、教材来源、审核记录及向量索引，参见 [模型接入](docs/yolo-integration.md)和[教材检索](research/retrieval/README.md)。

## 第一步：数据库 SQL

使用本地 MySQL 时，在 DataGrip 或 MySQL 客户端用有建库权限的账号依次执行：

1. `sql/00_create_database.sql`：创建 `tongue_analysis` 数据库。
2. `sql/01_schema.sql`：创建业务表与索引，仅用于尚未建表的数据库。
3. 如需独立应用账号，修改 `sql/02_local_user.sql.example` 的密码后执行。将相同密码写入 `.env` 的 `DATABASE_URL`。

空库可只执行第 1 个 SQL，然后用 `alembic upgrade head` 建表。若已执行第 2 个 SQL，使用 `scripts/init_mysql.py` 核对旧表、标记 `0001` 并执行后续增量迁移。

| 表 | 内容 |
|---|---|
| users | 用户、账号类型、密码散列、会话版本、个人信息 |
| stored_files | 私有舌象图片与来源文件的索引 |
| analyses | 输入、任务进度、模型原始结构化输出、错误状态 |
| reports | 报告内容、模型版本、模拟标记 |
| report_evidence | 生成报告时的实体、关系路径、出处快照 |
| documents | 已上传来源文档的文件索引与元信息 |
| audit_logs | 实际发生的操作与系统事件 |
| alerts | 分析失败等事件的待处理告警 |

Neo4j 使用 `knowledge/scripts/init.cypher` 建立约束和索引；可直接在 Neo4j Browser 执行，或在配置后运行 `python knowledge/scripts/init_graph.py`。实体是 `KnowledgeEntity`，来源是 `Source`，关联是 `RELATES_TO`，实体与来源通过 `FROM_SOURCE` 连接。来源的权威数据保存在 Neo4j，MySQL 的 documents 只用于已上传文档索引。

## 推荐启动：Docker数据库与后端 + 本地小程序

前提：Python 3.11/3.12、Node 20.19+ 或 Node 22/24、Docker Desktop（已启动）、微信开发者工具。以下命令在 PowerShell 中运行。

```powershell
cd F:\code\tongue-analysis
python scripts/configure.py

docker compose --env-file .env -f deploy/compose.yml up -d --build
```

`configure.py` 创建 `.env` 和 `miniapp/.env`，生成随机本地密码与JWT密钥；如果 `.env` 已存在会停止，保留原文件。Docker启动 MySQL、Neo4j 和后端，MySQL镜像负责建库建账号，后端通过Alembic建表；走这一方式无需另外执行建表SQL。

初始化图谱索引，并按需加载标注清楚的联调样例：

```powershell
docker compose --env-file .env -f deploy/compose.yml exec backend python /srv/tongue/knowledge/scripts/init_graph.py
docker compose --env-file .env -f deploy/compose.yml exec backend python -m app.cli seed-graph
```

样例含5个已发布实体、1个待审核实体、4条关系、2个来源；均不是医学参考文献。重复执行不会覆盖同ID的已有数据。

启动小程序编译：

```powershell
cd miniapp
npm ci
npm run dev:mp-weixin
```

在微信开发者工具中导入：

```text
F:\code\tongue-analysis\miniapp\dist\dev\mp-weixin
```

将 `miniapp/src/manifest.json` 中 `mp-weixin.appid` 改为自己的 AppID；未填写时可使用工具允许的测试/游客模式查看界面。开发阶段使用本地HTTP后端时，在开发者工具“详情 → 本地设置”中关闭域名和HTTPS证书校验。保持编译终端运行，修改 `miniapp/src/` 后会重新生成代码。

包内已附通过编译的 `miniapp/dist/build/mp-weixin`，也可直接导入这个目录查看。修改源码或后端地址之后仍需重新编译，生成目录中的修改会在下次编译时被覆盖。

开发联调入口可切换用户端、知识管理、系统运维；它只在前端 `VITE_ENABLE_DEV_LOGIN=true`、后端 `APP_ENV=development` 且 `DEV_LOGIN_ENABLED=true` 同时开启时可用。

- 后端接口文档：http://127.0.0.1:8000/docs
- 存活检查：http://127.0.0.1:8000/health
- Neo4j Browser：http://127.0.0.1:7474（用户名 neo4j，密码见本机生成的 `.env`）
- 查看后端日志：`docker compose --env-file .env -f deploy/compose.yml logs -f backend`

已有MySQL占用3306时，可修改 compose 的主机端口为3307；容器内部连接仍使用3306。

## 本地Python后端：已有MySQL与Neo4j

```powershell
cd F:\code\tongue-analysis
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
python scripts/configure.py
```

如果已创建 `.env`，直接编辑它。将 `DATABASE_URL`、`NEO4J_URI`、`NEO4J_PASSWORD` 配置为已有服务。数据库密码含 `@`、`:`、`/`、`#` 等字符时，需要在连接URL中进行百分号编码；自动生成的密码不含这些字符。

```powershell
.\.venv\Scripts\python.exe scripts\init_mysql.py
cd backend
..\.venv\Scripts\python.exe ..\knowledge\scripts\init_graph.py
..\.venv\Scripts\python.exe -m app.cli seed-graph
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

内置队列工作器使用数据库持久化任务，在应用启动时恢复中断任务。此版本使用单个Uvicorn进程，运行时保持 `--workers 1`；不要同时启动两个后端实例读取同一个任务库。

## 不安装数据库的本地流程演示

这是可选的SQLite + JSON图谱适配器，仅用于联调；MySQL和Neo4j仍为正式实现。

在尚未生成 `.env` 的目录中：

```powershell
python scripts/configure.py --local-demo
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m app.cli seed-graph
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

已有配置时手动切换 `DATABASE_URL` 和 `GRAPH_PROVIDER`；切换数据库不会自动搬迁已有数据。JSON图谱适配器只允许在development模式使用，且同样只运行一个进程。

## 微信登录与真实管理员

普通用户登录使用微信 `code2Session`，在后端 `.env` 配置 `WECHAT_APPID`、`WECHAT_SECRET`。AppSecret仅保存在后端。未配置时，微信登录接口返回明确的未配置状态。

真实管理员通过本地命令创建，密码交互输入，不写入源码：

```powershell
# Docker方式，在项目根目录运行
docker compose --env-file .env -f deploy/compose.yml exec backend python -m app.cli create-admin --username knowledge_admin --role knowledge_admin
docker compose --env-file .env -f deploy/compose.yml exec backend python -m app.cli create-admin --username ops_admin --role ops_admin
```

本地Python方式在backend目录执行 `python -m app.cli create-admin ...`。账号已存在时不会覆盖。页面没有“角色与权限”功能。上线时将 `APP_ENV=production`、`DEV_LOGIN_ENABLED=false`、前端 `VITE_ENABLE_DEV_LOGIN=false`，使用HTTPS后端并配置微信合法请求、上传和下载域名。

真机调试时，手机的127.0.0.1指向手机自身：把 `miniapp/.env` 中 `VITE_API_BASE_URL` 改为电脑的局域网IP，重启编译，并确保后端监听0.0.0.0、电脑防火墙允许相应端口。

## 已实现功能

- 用户端：拍照/相册、症状标签与文本、持续时间、上传与任务轮询、失败重试、分析完成页、报告、知识依据弹层、中文PDF导出、我的、历史搜索与分页、个人资料。
- 知识管理端：知识统计、分类与搜索、实体/别名维护、关系维护、草稿/待审核/发布、来源文档上传/查看/修改、图谱浏览、节点展开、来源查看、缩放和平移。
- 运维端：实际服务探测、模拟状态标识、当日分析数、报告总数、告警、操作与异常日志、日期/关键词筛选、普通用户启停、个人操作记录、密码修改、退出登录。
- 权限由后端校验；图片、报告与PDF都需要有效登录，其他用户不能通过ID读取。

## 模型训练完成后接入

详见 `docs/model-integration.md`。保留两个适配器：`mock` 是固定模拟数据；`http` 把图像文件与症状传给独立推理服务。

```dotenv
MODEL_PROVIDER=http
MODEL_BASE_URL=http://127.0.0.1:8001
MODEL_API_KEY=与你的推理服务一致
MODEL_TIMEOUT_SECONDS=120
```

Docker后端访问Windows宿主机上的模型服务时，地址使用 `http://host.docker.internal:8001`。模型服务需监听0.0.0.0。`model-service` 是接入边界，未实现训练模型时 `health.ready=false`、推理返回503，不会返回伪造预测。

图谱检索当前是可解释的词项匹配、最多两跳扩展与排序基线；报告当前由证据约束模板组织。神经网络融合模型、学习式重排序或大模型报告生成均未冒充实现。

## 验证与后续工作

```powershell
# 安装测试依赖，在项目根目录
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q backend/tests

# 服务运行且开发登录已开启时，验证真实部署栈
.\.venv\Scripts\python.exe scripts/verify_stack.py --base-url http://127.0.0.1:8000

cd miniapp
npm run typecheck
npm run build:mp-weixin
```

当前验证记录在 `docs/validation.md`：小程序构建、类型检查、17项后端测试、迁移检查及本地适配器HTTP流程已通过。当前环境没有Docker/MySQL/Neo4j服务及微信开发者工具，因此未宣称完成这些服务的实机联调或微信真机测试。可在你的机器启动上述服务后运行同一HTTP检查脚本。

待接入：训练权重与真实推理、真实图谱资料及出处、微信AppID/AppSecret、正式服务域名。模型接入无需改动小程序的数据结构。

## 目录

```text
tongue-analysis/
├── miniapp/                 # 小程序源码、依赖锁文件、已编译微信工程
├── backend/                 # API、业务流程、MySQL模型、图谱仓储、模型适配器、迁移、测试
├── model-service/           # 训练完成后的独立推理服务接口
├── sql/                     # 建库与建表SQL
├── knowledge/               # 图谱格式、示例数据、初始化及导入脚本
├── research/                # 训练、评估和实验结果目录
├── storage/                 # 运行时私有文件（源码包不附实际运行数据）
├── deploy/                  # Docker配置
├── scripts/                 # 初次配置、运行栈验证
└── docs/                    # 接口、模型、原型映射与验证说明
```
