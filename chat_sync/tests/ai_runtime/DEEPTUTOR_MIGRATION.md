# CHAT-AI-029H DeepTutor 迁移登记

参考版本：`LookHealthClient/DeepTutor-main`（Apache License 2.0）  
登记日期：2026-08-27  
许可证核查结论：**允许**按 Apache 2.0 复用协议、纯函数与算法语义；**禁止**复制进程内 Session、PocketBase/SQLite、WebSocket 协议、StreamBus 传输实现、账号/知识库/健康权限模型。Spark 生命周期一律由 Run、Checkpoint、ToolCall、PendingInteraction、Event、Outbox 承载。

## 1. 工单 3.3 对照表

| DeepTutor 部分 | 源文件 | 迁移方式 | Spark 落点 | 许可证 | 说明 |
|---|---|---|---|---|---|
| `ToolDefinition` / `ToolParameter` | `deeptutor/core/tool_protocol.py` | 直接复用语义，重建 DTO | `chat_sync/ai_runtime/protocols/tool_protocol.py` | Apache-2.0 | 保持 JSON Schema 语义，增加 Spark `target` / `execution_mode` |
| `ToolResult` | `deeptutor/core/tool_protocol.py` | 直接复用四路语义 | `ai_runtime/protocols/tool_protocol.py`、`ai_models/tool.py` | Apache-2.0 | `content` / `metadata` / `sources` / `pause_for_user`；暂停写入 PendingInteraction，不走进程内 queue |
| `ToolPolicy` | `deeptutor/runtime/registry/tool_registry.py` 判定思想 | 直接复用判定思想 | `ai_runtime/tools/policy.py` | Apache-2.0 | 绑定用户、Run、平台、权限快照；非法 `target`/`execution_mode` 拒绝 |
| Schema 校验 | `deeptutor/core/agentic/tool_dispatch.py` | 直接复用纯校验规则 | `ai_runtime/tools/policy.py` `validate_schema`、`dispatcher.py` | Apache-2.0 | 先校验模型参数，再校验 Policy |
| 参数 canonical hash | DeepTutor 去重键语义 | 直接复用算法 | `ai_runtime/tools/policy.py` `canonical_tool_args`、`ai_models/tool.py` | Apache-2.0 | 用于重复调用、幂等和审计，不暴露原始参数 |
| `ask_user` payload 规范化 | `deeptutor/tools/ask_user.py` | 直接复用规范化语义 | `ai_runtime/tools/ask_user_schema.py`、`ai_services/pending_interaction_service.py` | Apache-2.0 | 稳定 `question_id`，限制题数/选项/文本/schema_version=2 |
| 工具重复调用检测 | `deeptutor/core/agentic/tool_dispatch.py` | 直接复用判定算法 | `ai_runtime/tools/dispatcher.py` | Apache-2.0 | 与 DB 唯一约束、Worker 重试共同生效 |
| Agent Loop 最大轮次/强制结束 | `deeptutor/core/agentic/loop.py`、`deeptutor/agents/chat/agent_loop.py` | 直接复用控制算法 | `ai_runtime/agentic/loop.py` | Apache-2.0 | 每 round 写 checkpoint，终止状态写入 Run/Event |
| Think/Reasoning 流式分类 | `deeptutor/agents/chat/agent_loop.py` `InlineThinkFilter` | 直接复用分类算法 | `ai_runtime/agentic/think_filter.py`、`ai_services/stream_writer.py` | Apache-2.0 | 转为可回放 Event/Block，不混入最终正文 |
| `ToolRegistry` | `deeptutor/runtime/registry/tool_registry.py` | 部分迁移 | `ai_runtime/tools/registry.py` | Apache-2.0 | 加入 version/target/platform/权限/风险/超时/`execution_mode` |
| `ScopedToolRegistry` | `deeptutor/runtime/registry/scoped_registry.py` | 部分迁移 | `ai_runtime/tools/scoped_registry.py` | Apache-2.0 | scope 固化为 Run 快照，恢复不得漂移 |
| `dispatch_tool_calls` | `deeptutor/core/agentic/tool_dispatch.py` | 部分迁移 | `ai_runtime/tools/dispatcher.py` | Apache-2.0 | 校验、并行、去重；结果落库可恢复 |
| `execute_tool_call` | `deeptutor/core/agentic/tool_dispatch.py` | 部分迁移 | `ai_runtime/tools/executor.py`、`pending_interaction_service.py` | Apache-2.0 | server 在 Worker 执行；`ask_user` 为 `target=server` + `execution_mode=pause` |
| `AgentLoop` | `deeptutor/core/agentic/loop.py`、`deeptutor/agents/chat/agent_loop.py` | 部分迁移 | `ai_runtime/agentic/round_runner.py`、`loop.py` | Apache-2.0 | think/act/observe/respond；由 Run/Checkpoint 驱动 |
| StreamBus 事件语义 | `deeptutor/core/stream_bus.py` | 部分迁移（仅语义） | `ai_models/event.py`、`ai_services/stream_writer.py`、`ai_tasks/outbox_tasks.py` | Apache-2.0 | 传输改为 Event + Outbox；不复制 StreamBus |
| Tool prompt hints | DeepTutor tool composition / prompt blocks | 部分迁移 | `ai_services/prompt_assembler.py` | Apache-2.0 | 只注入已过滤 Tool Manifest |
| deferred tools / `load_tools` | `deeptutor/tools/builtin/__init__.py` `load_tools` | 部分迁移 | `ai_runtime/tools/deferred.py` | Apache-2.0 | Capability/权限/平台过滤；本轮不实现完整 MCP |
| checkpoint | DeepTutor 进程内 transcript | 部分迁移 | `ai_models/tool.py` `ChatAgentCheckpoint`、`ai_models/context.py` | Apache-2.0 | 可序列化快照；恢复时不重复追加 `role=tool` |

## 2. 明确禁止迁移（保持登记，避免回流）

| DeepTutor 部分 | 源文件 | 决定 |
|---|---|---|
| 进程内 reply queue | `core/agentic/loop.py` | 不迁移；Spark 用同一 Run 的 `WAITING_*` + resume 任务 |
| PocketBase / SQLite Session | `services/session/pocketbase_store.py`、`sqlite_store.py` | 不迁移 |
| DeepTutor WebSocket 协议与 Web 组件 | `core/stream_bus.py`、DeepTutor `web/` | 不迁移；chat-web 消费 Spark Event/Block |
| 账号、文件、知识库、健康权限模型 | `multi_user/*`、RAG/KB | 不迁移 |
| 写工具 / MCP / exec / imagegen / 完整 HealthKit 客户端 | `tools/*`、`services/mcp/*` | 本工单不引入 |

## 3. CHAT-AI-029 本轮 Spark 适配说明

- Provider 只看到 OpenAI function schema；`target` / `execution_mode` / 平台元数据在 `provider_tool_schemas()` 剥离。
- `ask_user` 公开卡片使用 canonical `toolQuestionCards`，不再投影 `searchSummary`。
- 公开投影不包含原始 arguments、token、健康原文或 `free_text`；日志对 `answers` / `free_text` / `claim_token` 脱敏。
- `target=client` 端到端 claim/执行验证延后到后续工单；本轮只保留服务端 stub、平台过滤与 claim/heartbeat 测试。

## 4. 验收指针

- 契约：`chat_sync/tests/contracts/schemas/pending_interaction.v1.schema.json`
- 服务：`chat_sync/tests/ai_services/test_pending_interaction_service.py`、`chat_sync/tests/ai_runtime/test_tool_manifest.py`
- Web：`chat-web/tests/interaction.test.tsx`
