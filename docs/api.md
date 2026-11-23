# 接口索引

运行后以 `/docs` 或 `/openapi.json` 为完整字段说明。业务前缀 `/api/v1`；登录之外均发送 `Authorization: Bearer JWT`。

| 接口 | 方法 | 权限/用途 |
|---|---|---|
| /auth/wechat | POST | 微信code登录普通用户 |
| /auth/login | POST | 管理员账号密码登录 |
| /auth/dev-login | POST | 仅开发环境联调登录 |
| /auth/logout | POST | 当前账号所有已有会话失效 |
| /users/me | GET / PUT | 本人信息 |
| /users/me/password | POST | 验证原密码后修改，并失效旧会话 |
| /users/me/logs | GET | 本人最近100条操作 |
| /uploads?purpose=image | POST | 登录用户上传图片 |
| /uploads?purpose=document | POST | 知识管理员上传来源PDF/TXT |
| /uploads/{id}/content | GET | 文件所有者；知识管理员可读来源文档 |
| /analyses | POST | 普通用户创建排队任务，返回202 |
| /analyses/{id} | GET | 本人任务进度 |
| /analyses/{id}/retry | POST | 本人失败任务重试 |
| /reports | GET | 本人报告历史，q/page/page_size |
| /reports/{id} | GET | 本人报告 |
| /reports/{id}/evidence | GET | 本人报告的生成时证据快照 |
| /reports/{id}/pdf | GET | 本人中文PDF |
| /knowledge/overview | GET | 知识管理员统计 |
| /knowledge/entities | GET / POST | 查询/新建实体 |
| /knowledge/entities/{id} | PUT / DELETE | 修改/删除实体 |
| /knowledge/entities/{id}/publish | POST | 待审核实体发布 |
| /knowledge/relations | GET / POST | 查询/新建关系 |
| /knowledge/relations/{id} | PUT / DELETE | 修改/删除关系 |
| /knowledge/relations/{id}/publish | POST | 待审核关系发布 |
| /knowledge/sources | GET / POST | Neo4j来源与文档索引 |
| /knowledge/sources/{id} | PUT / DELETE | 修改/删除未被引用的来源 |
| /knowledge/graph | GET | q/entity_id/kind，单次最多80实体 |
| /operations/overview | GET | 运维实际探测与统计 |
| /operations/logs | GET | 运维日志，q/category/date/page/page_size |
| /operations/alerts | GET | 最近100条告警 |
| /operations/alerts/{id}/resolve | POST | 标记已检查的告警为已处理 |
| /operations/users | GET | 普通用户分页列表 |
| /operations/users/{id}/status | PUT | 普通用户启用/停用，失效旧会话 |
| /operations/configuration | GET | 无密钥的当前运行配置 |

更新接口使用PUT以兼容微信小程序支持的请求方法。常见状态码：401登录失效，403角色权限不足，404不存在或不属于本人，409知识依赖/状态冲突，413文件超限，422格式校验失败，503数据库/图谱/微信外部服务不可用。

分析任务状态为queued、running、completed、failed。结果与证据快照在同一MySQL事务提交，每个分析任务至多一份报告。文件下载不使用公开静态目录，不将JWT放在URL中。

数据库时间统一存UTC，接口输出显式UTC偏移，前端显示北京时间。当日分析与日志日期筛选均使用Asia/Shanghai的日期边界。
