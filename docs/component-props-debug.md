# 小程序组件属性排查

## 调试现场

通过本机微信开发者工具内置接口检查以下项目：
`F:\code\tongue-analysis\tongue-analysis\miniapp\dist\build\mp-weixin`。
该目录是本项目唯一的 mp-weixin 构建目录。
在源码临时加入 Component 注册拦截，重新构建并完整刷新后，模拟器可读取到本次特有的诊断标记及 attached 记录，确认该轮运行使用本次产物。
临时拦截和诊断标记已从最终源码和产物移除。

## 捕获结果及结论边界

- 刷新前，在 `pages/report/index` 捕获 `components/AppIcon`：`typeof uP === 'string'`，但值为字面量 `e1`，Vue name 缺失，图片路径为 `/static/icons/undefined.png`。
- uni-app 正常的 uP 形如 `组件uid,props缓存下标,更新计数`，用于查找 Vue props。字面量 `e1` 不能定位这些 props，因此可以解释该实例的 name 丢失。
- RoleNav 源码各角色的 tab.icon 都有定义，静态文件也齐全。模拟器中导航的 AppIcon 实际接收到 `leaf`、`user`，uP 为正常字符串引用。
- 在 attached 拦截启用后的刷新、页面打开过程中，没有捕获到非字符串 uP 或 attached 抛错；报告页异步加载后的 AppIcon 也正常。
- 原始 `e1.split is not a function` 本次没有再次复现，因此**不能证实两条错误来自同一个组件实例**，也不能将 RoleNav 的 tab.icon 判为根因。刷新前后的差异提示旧运行态/编译缓存与磁盘产物不同步的可能，具体来源未确定。

## 实际调整

- `miniapp/src/components/AppIcon.vue`：name 为空时不生成 image，避免请求 undefined.png。不使用默认图标掩盖缺失的业务参数。
- 当前调试工程 `project.private.config.json`：关闭 `compileHotReLoad`，重新完整构建、刷新，减少编译时混用旧组件状态的可能。此项是本地调试设置。
- RoleNav 数据保持原实现。临时 attached 诊断已移除；`main.ts` 恢复原状。

## 验证

- `npm run typecheck`：通过。
- `npm run build:mp-weixin`：通过。
- 最终构建在开发者工具完整刷新后，“我的”页面及 RoleNav 的图标属性、图片路径正常。
- 当前已登录账号的报告页面正常打开，AppIcon 实际参数为：
  - download，uP `44,1,1`，图片 `/static/icons/download.png`；
  - book，uP `44,2,1`，图片 `/static/icons/book.png`；
  - leaf，uP `44,3,1`，图片 `/static/icons/leaf.png`。
- 报告页截图已实际查看，按钮与舌象特征图标正常：`storage/props-report-after.jpg`。
- 完成上述操作后，查询开发者工具返回的 `split is not` / `undefined.png` 日志，无匹配行。该结果仅表示此次操作未再捕获，不证明原始 split 异常的根因已定位。

若原始 split 异常再次出现，应在其首次抛出时保留实际组件路径、uP 的类型和值以及当前页面；不应仅凭调用栈推断是 RoleNav。
