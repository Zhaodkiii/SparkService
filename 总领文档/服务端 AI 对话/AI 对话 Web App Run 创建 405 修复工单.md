# AI 对话 Web App Run 创建 405 修复工单

工单编号：`CHAT-WEB-018`  
阶段归属：P1「认证、Run 控制面与 Mock」维护工单；问题在 P3 联调时暴露，不改变其基础设施归属。  
状态：已修复，待真实登录态联调验收。  
影响范围：Web 通过 Next.js BFF 调用 Spark Django REST API 的全部带尾斜杠接口，Run 创建最先触发。

## 一、问题现象

Web 创建一轮对话时请求：

```http
POST /api/v1/ai/chat/threads/{thread_id}/runs/
```

浏览器最终收到 `405 Method Not Allowed`，页面显示统一兜底文案“请求未完成，请稍后重试”。服务端日志呈现以下链路：

```text
Web intent:   POST /api/v1/ai/chat/threads/{id}/runs/
Next proxy:   POST /api/v1/ai/chat/threads/{id}/runs
Django:       301 Location: /api/v1/ai/chat/threads/{id}/runs/
fetch follow: GET  /api/v1/ai/chat/threads/{id}/runs/
Django:       405 Allow: POST, OPTIONS
```

这不是 Run View 缺少 `POST`，也不是认证、请求体或幂等键错误。`CreateRunView` 的规范路由本来就只允许 `POST /runs/`。

## 二、根因分析

### 2.1 直接根因

`chat-web/app/api/v1/[...path]/route.ts` 使用 catch-all 动态路由参数重新拼接上游地址：

```ts
const upstreamPath = `/api/v1/${path.join("/")}`;
```

动态参数只包含路径 segment，不包含原请求末尾的 `/`，也不包含 query string。因此 BFF 把规范地址 `/runs/` 改成 `/runs`。

Django 开启尾斜杠规范化后，对无斜杠地址返回 `301`。Node Fetch 默认跟随重定向；依据 301/302 的兼容行为，`POST` 可能被改写为 `GET`。重定向后的规范地址只允许 `POST`，于是返回 405。

### 2.2 防线为什么没有发现

- `tests/wire-api.test.ts` 只验证 `SparkRunApi` 交给 HTTP client 的 URL 带 `/`，没有覆盖 Next BFF 到 Django 的第二跳。
- BFF 没有“路径字节级保真”测试，尾斜杠和 query string 丢失未被发现。
- 上游 Fetch 使用默认 `redirect: "follow"`，把第一次 301 隐藏成第二次 405，错误日志没有直接暴露重定向契约错误。
- 统一错误提示只能正确兜底展示，不能修复代理改变 HTTP 方法的问题。

## 三、修复方案

### 3.1 已实施修改

| 文件 | 修改 | 目的 |
| --- | --- | --- |
| `chat-web/app/api/v1/[...path]/route.ts` | 从原始 `Request.url` 提取上游 path，不再由 catch-all params 重建 | 保留尾斜杠、百分号编码和 query string |
| `chat-web/lib/server/upstream.ts` | 新增 `sparkApiPathFromRequest`；上游 Fetch 使用 `redirect: "manual"` | 限定代理命名空间，并阻止 301/302 隐式改写 POST |
| `chat-web/next.config.ts` | 启用 `skipTrailingSlashRedirect` | 让 Route Handler 收到原始尾斜杠语义 |
| `chat-web/tests/api-proxy-path.test.ts` | 增加路径保真、命名空间和重定向测试 | 覆盖 BFF 第二跳回归 |

### 3.2 明确不采用的方案

- 不在 Django 增加一套无尾斜杠重复路由。服务端规范路由保持单一，避免两套 URL 长期漂移。
- 不把 405 仅映射为更友好的 Toast。提示优化不能代替协议修复。
- 不允许 BFF 自动跟随 API 重定向。任何 3xx 都应作为代理/契约问题直接暴露。

## 四、实施与验证步骤

### 4.1 自动化验证

```bash
cd /Users/hua/Documents/project/Reference/SparkService/chat-web
pnpm exec vitest run tests/api-proxy-path.test.ts tests/wire-api.test.ts
pnpm typecheck
```

当前结果：2 个测试文件、8 个测试全部通过，TypeScript 类型检查通过。

生产构建后的 BFF 冒烟请求使用相同 Run 地址、无登录凭证发送 `POST`，返回预期的 `401 Authentication credentials were not provided`，且响应保留 `X-Request-ID: chat-web-018-smoke`。这证明请求已以 `POST .../runs/` 到达 Django 鉴权层，没有再经过 301/GET/405 链路；真实 Run 创建仍需登录态完成业务验收。

### 4.2 真实联调步骤

1. 重启 Next dev server，使 `next.config.ts` 变更生效。
2. 保持 Django 服务运行在 `SPARK_INTERNAL_API_BASE_URL` 指定地址。
3. 使用真实登录态创建一个新 Thread，发送一条纯文本消息。
4. 以同一个 `X-Request-ID` 对照 Web 与 Django 日志。
5. 确认 Django 第一次收到的就是 `POST .../runs/`，请求只出现一次且没有 301。
6. 确认 `Authorization`、`Idempotency-Key`、`Content-Type`、请求体未丢失。
7. 确认响应进入正常 Run 创建语义；允许 2xx 或明确的业务 4xx，不得再出现重定向派生的 405。

## 五、验收标准

- [x] `SparkRunApi.create` 生成的规范地址以 `/runs/` 结尾。
- [x] Next BFF 保留传入 pathname 的尾斜杠和 query string。
- [x] 上游 Fetch 不自动跟随 3xx。
- [x] BFF 只允许 `/api/v1/` 命名空间作为上游路径。
- [x] 定向 Vitest 与 TypeScript 检查通过。
- [ ] 真实登录态下 Run 创建成功。
- [ ] Django 日志不存在 `POST /runs -> 301 -> GET /runs/ -> 405`。
- [ ] 同一发送意图只创建一个 Run，幂等键未因重试或重定向丢失。

## 六、统一错误提示与观测要求

- 如果未来再次收到 3xx，BFF 应保留原状态并记录 `api.proxy.unexpected_redirect`，不得伪装成 405。
- 405 可继续进入 `CHAT-WEB-016` 的统一错误系统，但必须携带 `request_id`；用户界面不得展示 Django HTML。
- 生产告警建议增加：`run.create` 的 3xx/405 比例、BFF 上游重定向次数、同一 `request_id` 的方法变化。
- 用户点击“重试”必须复用原发送意图的幂等键，不能因传输错误产生重复 Run。

## 七、回滚说明

若变更引发其他 API 兼容问题，可分别回滚路径保真和手动重定向设置；不得通过恢复 catch-all params 拼接来长期运行。回滚期间应直接修正受影响 API 的规范 URL，并保留 `redirect: "manual"` 防线。
