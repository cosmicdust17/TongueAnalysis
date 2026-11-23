# 微信登录联调记录（2026-11-18）

实际项目根目录为 `F:\code\tongue-analysis\tongue-analysis`。工作区及父级未找到 `AGENTS.md`。
后端先读取内层 `.env`，再由 `F:\code\tongue-analysis\.env` 覆盖；进程环境变量优先级最高。
本次将已填写的微信配置同步到外层有效配置，并将 AppID 同步到实际源码 `miniapp/src/manifest.json`。
不在本文记录任何登录凭证或密钥。

## 修改

- `backend/app/api/auth.py`：复用 `/api/v1/auth/wechat`、现有 JWT 和 MySQL users；按 openid 创建/复用普通用户，处理并发首次创建、禁用账号、失效凭证、微信配置错误、频率限制、网络异常及异常响应。不回传微信原始错误或会话密钥。
- `backend/app/main.py`：关闭 HTTP 客户端的普通请求/调试日志，避免记录微信请求查询参数。
- `backend/app/api/operations.py`：在已有管理员配置接口中返回公开的 AppID 和是否已配置标记，用于核对运行实例；不返回 AppSecret。
- `miniapp/src/pages/login/index.vue`：每次点击重新调用 uni.login，阻止重复点击，为获取凭证失败/空凭证提供提示。保留管理员账号登录、开发入口和页面结构。
- `miniapp/src/stores/auth.ts`：登录时清除上一账号的未完成分析状态；继续保存系统登录状态并按角色进入首页。
- `miniapp/src/manifest.json` 与 `miniapp/dist/build/mp-weixin`：同步 AppID 并重新构建。
- `backend/tests/conftest.py`：测试隔离真实微信配置。
- `backend/tests/test_wechat.py`：增加微信登录和错误分支回归测试。

## 实际通过

1. `npm run typecheck`、`npm run build:mp-weixin`。
2. `python -m pytest -q backend/tests --tb=no`：34 项通过；有一条现有测试客户端依赖弃用提示。
3. 源码、编译工程和有效后端配置的 AppID 一致；前端源码/编译产物不含配置的 AppSecret。
4. 已重启 8000 端口后端，通过管理员配置接口确认运行实例加载了对应 AppID 和已填写的微信配置；本地 API 可访问。
5. 实际请求微信接口的无效测试凭证诊断返回 401 和“微信登录凭证已失效，请重新点击微信登录”。该结果仅证明接口可达并能处理微信响应，不代表真实账号登录已验收。
6. 自动测试使用模拟微信响应、独立 SQLite 测试库，覆盖首次创建普通用户、退出使旧会话失效、重登复用用户、报告历史保留、与开发账号历史隔离、禁用用户和错误提示。不会把测试数据库结果描述成真实微信或 MySQL 账号验收。

## 开发者工具验收步骤（待执行）

当前没有可用的开发者工具或手机控制接口，未获取真实微信登录凭证。**真实微信首次登录、退出重登和微信账号对应的 MySQL 历史验收待验证。**

1. 在微信开发者工具重新导入：
   `F:\code\tongue-analysis\tongue-analysis\miniapp\dist\build\mp-weixin`。
   确认“详情”中的 AppID 是你的 AppID。电脑模拟器本地联调时，在“详情 → 本地设置”启用“不校验合法域名、web-view（业务域名）、TLS版本以及HTTPS证书”。
2. 点击“编译”。如果仍保存开发账号登录状态，先进入“我的”底部退出并确认，返回登录页。
3. 点击“微信登录”，不要点击“开发联调入口”。预期进入普通用户“舌象分析”首页；管理员账号登录仍保留。
4. 用于流程演示时上传一张测试图片、填写症状和持续时间、提交分析；等待生成明确标注为模拟的报告。进入“我的 → 历史记录”，打开报告并尝试导出 PDF。
5. 从“我的”退出并确认，再点击“微信登录”。预期使用新凭证登录，复用原有 MySQL 用户；“我的 → 历史记录”仍可打开步骤 4 的报告。如果微信账号原本已有报告，直接检查该报告即可。
6. 数据库中核对 `users` 的微信普通用户记录数量没有因重复登录增加；对应报告的 `user_id` 不变。只核对关联关系，不复制或分享身份字段、请求体、登录响应或完整微信请求地址。
7. 开发联调账号的历史不会自动转入微信账号；切换回开发账号后其原有历史仍属于它。

如出现“配置异常”，检查有效 `.env` 的微信配置是否与小程序 AppID 对应，以及微信平台的服务器 IP 白名单；改完后重启后端。
如出现“凭证已失效”，重新点击微信登录获取新凭证，不重复发送之前的凭证。
真机访问时，`127.0.0.1` 指向手机自身，需将 `miniapp/.env` 的 `VITE_API_BASE_URL` 改为手机可访问的电脑局域网地址并重新构建；正式环境使用已配置合法域名的 HTTPS 后端。

## 复现构建与测试

```powershell
cd F:\code\tongue-analysis\tongue-analysis\miniapp
npm run typecheck
npm run build:mp-weixin
cd ..
.\.venv\Scripts\python.exe -m pytest -q backend/tests --tb=no
```

未修改模型、训练、Neo4j、数据库表结构；未合并开发账号与微信账号数据。
