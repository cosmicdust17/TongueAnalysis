# 健康趋势后端与前端接口交接

项目为 `F:/code/tongue-analysis/tongue-analysis` 的 `main` 分支。独立界面 worktree 的分支是 `ui-redesign`。

## 1. 后端总结

- `backend/app/api/health_trends.py` 实现症状追踪、自评、趋势和完成页建议。对同一用户的变更先锁定 MySQL 用户行，再校验名额和写入。在 SQLite 开发或测试环境使用写事务锁。
- `backend/app/schemas/__init__.py` 为旧分析请求增加可选的 `confirmed_symptoms`。它记录用户点选或复核后的症状，原有 `symptoms` 继续作为报告原文。完成页建议按需查询，分析 worker 和报告组装继续走原流程。
- `backend/app/api/reports.py` 增加月历有记录日查询及历史日期筛选，复用现有报告 ID、分页和详情接口。
- `backend/migrations/versions/0002_health_trends.py` 新增三张表，分别保存追踪、每日自评和明确拒绝。分析表新增可空的确认症状列，MySQL 分析提交时间改为微秒精度，方便比较短时间内连续提交的分析。已有分析的症状原文、报告和舌照继续按原路径读取。
- `scripts/init_mysql.py` 继续支持空库和由旧 SQL 创建的数据库。它先按 `0001` 核对旧表，有旧表且无版本的库核对通过后只标记 `0001`，随后执行增量迁移。已有 `0001` 的库直接升级。工具完成后核对当前 ORM 结构。

在仓库根目录，使用有效 `DATABASE_URL` 的 MySQL 配置执行：

```powershell
.\.venv\Scripts\python.exe scripts\init_mysql.py
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini current
```

版本目标为 `0003`。`0002` 数据库沿用已有数据，使用 Alembic 增量增加首次开启追踪日期。已有 Alembic 版本记录的数据库执行：

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
```

迁移完成后重启后端。已有库沿用 Alembic 做结构升级，`AUTO_CREATE_SCHEMA` 只负责创建缺失的表。旧 `sql/01_schema.sql` 对应 `0001`。从这份 SQL 建表的数据库要执行新增迁移，单独标记 `head` 会跳过建表与加列。

### 验证与限制

- 回归命令为 `.\.venv\Scripts\python.exe -m pytest -q backend/tests`。实测 57 项通过，有一条已有的 Starlette 弃用提示。新增测试覆盖旧客户端、建议过滤、重复及并发开启、每日 0 分和空值、同日更新、停止并恢复、权限隔离、跨月日边界及同天多份报告。
- 已在隔离 MySQL 8.0.43 实例验证空库升级、旧 SQL 建表的库升级、重复运行初始化工具和五组接口验收。2026-11-24 核对日常运行实例时，业务库已为 `0002`。
- 建议比较的是当前分析与上一次已完成分析的显式确认症状。没有结构化确认的旧分析以空数组参与比较。完成页重复查询可以看到仍然符合条件的建议，除非用户明确拒绝、已经开启追踪或名额用完。停止腾出名额并保留历史，手动恢复沿用原追踪 ID。
- 症状身份按名称规范化确定。首版复用已有标签“口干”“乏力”“睡眠不佳”，也接受用户确认的新名称。合并首尾及内部空白、统一 Unicode 宽度及字母大小写用于去重。不同写法如“失眠”和“睡眠不佳”保留为两项。
- 自评只写服务端今天。停止的项目可以读趋势，恢复后可以再次提交今日等级。

## 2. 接口交接清单

全部使用 `Authorization: Bearer <系统 JWT>`，要求 `user` 角色。JSON 写操作使用 `Content-Type: application/json`。数据所有者来自 JWT，前端不用传 `user_id`。以下均为完整路径，现有小程序 `api()` 已自动拼接 `/api/v1`，传入该工具函数时去掉这段前缀。

### 2.1 提交分析和轮询

**`POST /api/v1/analyses`**

```json
{
  "image_id": "file-id",
  "symptoms": "口干，乏力，近几天睡眠较浅",
  "duration": "近一周",
  "confirmed_symptoms": ["口干", "乏力"]
}
```

`confirmed_symptoms` 可省略，默认为 `[]`。最多 20 项，规范化后每项 1–80 字，保持用户确认顺序。现有标签可以直接提交标签文本。自由输入的长句仍填 `symptoms`，只有用户确认其为独立症状时才提交为数组元素。旧客户端提交原来的三个字段即可。

**`GET /api/v1/analyses/{aid}`** 继续用于轮询，`aid` 是分析任务 ID。提交返回 `202`，轮询返回 `200`，两者结构相同。`status` 为 `queued`、`running`、`completed` 或 `failed`。下方为完成态；处理中 `report_id` 为 `null`。

```json
{
  "id": "analysis-id",
  "status": "completed",
  "progress": 100,
  "error": "",
  "report_id": "report-id",
  "created_at": "2026-11-23T10:40:00+00:00",
  "updated_at": "2026-11-23T10:40:01+00:00"
}
```

提交时图片无效或不属于本人返回 `400`。已有排队或运行中的任务返回 `409`，含 `detail.message` 和 `detail.analysis_id`。输入格式错误返回 `422`。轮询其他用户的任务返回 `404`。

### 2.2 完成页建议

**`GET /api/v1/health-trends/analyses/{analysis_id}/suggestion`**，无请求体和查询参数。

```json
{"suggestion": {"symptom_name": "口干"}}
```

空数据是 `200 {"suggestion": null}`，适用于没有显式确认的新症状、任务未完成、候选已追踪或已拒绝、追踪名额已满等。任务不存在或不属于本人返回 `404 {"detail":"分析任务不存在"}`。

**`PUT /api/v1/health-trends/analyses/{analysis_id}/dismissal`**，用于「暂不追踪」。请求体为 `{"symptom_name":"口干"}`，使用建议返回的名称。

```json
{"symptom_name": "口干", "dismissed": true}
```

重复提交相同拒绝仍返回 `200`。当症状并非该已完成分析的新增确认候选时返回 `409 {"detail":{"code":"suggestion_unavailable","message":"该症状不属于本次分析的可处理建议"}}`。任务不存在或不属于本人返回 `404`。拒绝只影响自动推荐，仍可走手动开启接口。离开页面无需发送此请求。

### 2.3 列表、开启与停止

**`GET /api/v1/health-trends/trackings`**，无参数。返回本人全部追踪项，启用项在前。`today_level` 是服务端今天的等级，`null` 表示未填。

```json
{
  "date": "2026-11-24",
  "max_active": 2,
  "active_count": 1,
  "items": [
    {"id":"tracking-id","symptom_name":"口干","active":true,"today_level":0},
    {"id":"paused-id","symptom_name":"乏力","active":false,"today_level":null}
  ]
}
```

无历史追踪项时返回 `200`，`active_count` 为 `0`，`items` 为 `[]`。

**`POST /api/v1/health-trends/trackings`**，用于「开始追踪」、手动添加和恢复。请求体为 `{"symptom_name":"口干"}`。新建、恢复、重复开启已启用项均返回 `200`。重复开启或恢复时返回原 `id`，没有自动自评。

```json
{"id":"tracking-id","symptom_name":"口干","active":true}
```

启用两项后，开启第三项或恢复占用新名额会返回：

```json
{
  "detail":{"code":"tracking_limit_reached","message":"最多同时追踪两项症状","max_active":2}
}
```

HTTP 状态为 `409`。此时对同一已启用症状重复调用仍返回 `200`。

**`PUT /api/v1/health-trends/trackings/{tracking_id}/stop`**，无请求体。停止或重复停止返回 `200`，历史和当天已存在的记录仍可读取。

```json
{"id":"tracking-id","symptom_name":"口干","active":false}
```

不存在或非本人项返回 `404 {"detail":"症状追踪项不存在"}`。

### 2.4 保存今日自评与趋势

**`PUT /api/v1/health-trends/trackings/{tracking_id}/checkins/today`**。请求体仅含 `level`，如 `{"level":0}`。整数 `0`、`1`、`2`、`3` 分别表示「没有」「轻微」「明显」「很明显」。同日再次提交会更新当天原记录。

```json
{"date":"2026-11-24","level":0,"level_name":"没有"}
```

停用项返回 `409 {"detail":{"code":"tracking_paused","message":"请先恢复追踪再填写自评"}}`。不存在或非本人项返回 `404`。字符串 `"0"`、布尔值、空值和范围以外的数字均返回 `422`。

**`GET /api/v1/health-trends/trackings/{tracking_id}/trend?start_date=2026-11-22&end_date=2026-11-25`**。两个参数都必填，格式 `YYYY-MM-DD`，范围含起止日。数据按北京时间的自然日升序返回。

```json
{
  "tracking_id":"tracking-id",
  "symptom_name":"口干",
  "started_date":"2026-11-24",
  "report_history":[
    {"date":"2026-11-22","mention_count":2,"report_id":"latest-matching-report-id"},
    {"date":"2026-11-23","mention_count":0,"report_id":null}
  ],
  "items":[{"date":"2026-11-24","level":0,"level_name":"没有"}]
}
```

- 开启前根据报告生成日统计。同一份已完成报告的原始症状自述提到症状多次只计一份，`report_id` 指向该日最新的匹配报告。有报告但均未提及时计为 `0`，当天无报告则省略该日。
- `items` 是开启当天及以后的已填自评，包含有效等级 `0`。未填写的日期省略。恢复追踪沿用首次开启日期。
- 旧追踪的首次开启日期未保存，返回 `started_date: null`、`report_history: []` 及现存自评。
- 开始晚于结束返回 `422 {"detail":"开始日期不能晚于结束日期"}`。不存在或非本人项返回 `404`。

### 2.5 分析记录日历

月历使用 `GET /api/v1/reports/calendar?month=YYYY-MM` 获取日期和份数，用 `GET /api/v1/reports?date=YYYY-MM-DD` 获取当日舌照报告。详见[分析记录月历接口交接](report-calendar.md)。

### 2.6 通用错误

| HTTP | 响应示例或格式 |
| --- | --- |
| 401 | `{"detail":"登录已过期，请重新登录"}` |
| 403 | `{"detail":"没有访问权限"}` |
| 404 | `{"detail":"症状追踪项不存在"}`。任务和报告对应各自的不存在提示。 |
| 409 | `detail` 为上述带 `code` 的冲突对象。现有分析任务有原状态冲突格式。 |
| 422 | FastAPI 校验返回 `{"detail":[{"loc":["body","level"],"msg":"…","type":"…"}]}`。业务日期范围校验可直接返回字符串 `detail`。 |
| 503 | `{"detail":"业务数据库暂时不可用，请检查数据库初始化和连接配置"}` |

## 3. 前端调用顺序

### 分析完成页

1. 提交分析时同时传用户点选或确认的 `confirmed_symptoms`。用既有任务接口轮询，读到 `completed` 后请求一次 `GET /api/v1/health-trends/analyses/{analysis_id}/suggestion`。
2. `suggestion: null` 时隐藏建议。否则展示返回的 `symptom_name`。「开始追踪」调用 `POST /api/v1/health-trends/trackings`。「暂不追踪」调用 `PUT /api/v1/health-trends/analyses/{analysis_id}/dismissal`。用户离开或刷新时按需重新读取。
3. 开启时遇到 `409 tracking_limit_reached`，展示服务端提示并刷新名额。一次完成页交互只展示一个建议，无需在用户选完后循环拉取下一项。

### 健康趋势页

1. 进入页面取 `GET /api/v1/health-trends/trackings`，读取 `date`、`active_count`、`max_active` 和追踪项。用 `today_level === null` 判断未填写，等级 `0` 显示「没有」。
2. 选中某项及日期范围时取 `GET /api/v1/health-trends/trackings/{tracking_id}/trend`。`report_history` 和 `items` 共用日期轴，在 `started_date` 处分段，缺失日期留空。
3. 点击带 `report_id` 的历史数据点打开原有报告详情。每日自评仍在舌象分析首页填写。暂停历史仍可展示，恢复使用原名称调用开启接口。

### 分析记录页日历

打开或切换月份、选中日期、打开报告的调用顺序见[分析记录月历接口交接](report-calendar.md)。自评和月历都按北京时间划分自然日，月历归属以舌照上传时间为准。
