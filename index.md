# Directory Index

## 根目录文件

- **[README.md](./README.md)** - 项目概述、启动命令与 Smoke Test 示例
- **[agent.py](./agent.py)** - LLM 代理核心循环与工具调度实现
- **[main.py](./main.py)** - FastAPI 应用入口、路由定义及会话管理
- **[tools.py](./tools.py)** - 租房 API 工具函数及 OpenAI function-calling 定义
- **[logger.py](./logger.py)** - 结构化日志事件追加写入 JSONL 文件
- **[requirements.txt](./requirements.txt)** - Python 依赖包列表

## docs/

- **[docs/index.md](./docs/index.md)** - 文档目录索引
- **[docs/interface.md](./docs/interface.md)** - Agent 对外接口规范及模型调用说明
- **[docs/interface_simulate.md](./docs/interface_simulate.md)** - 租房仿真 API 使用指导与接口列表
- **[docs/task.md](./docs/task.md)** - AI Agent 租房挑战赛任务说明书

## tests/

- **[tests/conftest.py](./tests/conftest.py)** - pytest 全局 fixture 与 mock 配置
- **[tests/test_agent_loop.py](./tests/test_agent_loop.py)** - Agent 循环逻辑单元测试
- **[tests/test_chat_endpoint.py](./tests/test_chat_endpoint.py)** - 聊天 API 端点集成测试
- **[tests/test_e2e_epic2.py](./tests/test_e2e_epic2.py)** - Epic2 会话管理端到端测试
- **[tests/test_init_houses.py](./tests/test_init_houses.py)** - 房源初始化 HTTP 请求测试
- **[tests/test_lifespan_http_client.py](./tests/test_lifespan_http_client.py)** - FastAPI 生命周期 HTTP 客户端测试
- **[tests/test_log_event.py](./tests/test_log_event.py)** - 结构化日志事件写入测试
- **[tests/test_logger.py](./tests/test_logger.py)** - 日志器功能覆盖测试
- **[tests/test_models.py](./tests/test_models.py)** - Pydantic 请求/响应模型验证测试
- **[tests/test_tools.py](./tests/test_tools.py)** - 工具函数行为单元测试

## logs/

运行时自动生成的会话日志目录，每个 `session_id` 对应一个 `.jsonl` 文件，记录 LLM 请求、工具调用和错误事件。

## _bmad-output/

BMAD 工作流产出物目录，包含项目规划与实现过程中生成的所有文档。

### _bmad-output/ 根文件

- **[_bmad-output/project-context.md](./_bmad-output/project-context.md)** - AI 代理执行规则与项目技术上下文

### _bmad-output/brainstorming/

- **[_bmad-output/brainstorming/brainstorming-session-2026-02-26.md](./_bmad-output/brainstorming/brainstorming-session-2026-02-26.md)** - 2026-02-26 项目头脑风暴会话记录

### _bmad-output/planning-artifacts/

- **[_bmad-output/planning-artifacts/architecture.md](./_bmad-output/planning-artifacts/architecture.md)** - 系统架构设计文档（完整版）
- **[_bmad-output/planning-artifacts/epics.md](./_bmad-output/planning-artifacts/epics.md)** - Epic 及用户故事完整定义
- **[_bmad-output/planning-artifacts/implementation-readiness-report-2026-02-27.md](./_bmad-output/planning-artifacts/implementation-readiness-report-2026-02-27.md)** - 实现就绪度评估报告
- **[_bmad-output/planning-artifacts/prd.md](./_bmad-output/planning-artifacts/prd.md)** - 产品需求文档（PRD）
- **[_bmad-output/planning-artifacts/prd-test-simulator.md](./_bmad-output/planning-artifacts/prd-test-simulator.md)** - 测试模拟器产品需求文档
- **[_bmad-output/planning-artifacts/prd-validation-report.md](./_bmad-output/planning-artifacts/prd-validation-report.md)** - PRD 结构与质量验证报告

### _bmad-output/implementation-artifacts/

- **[_bmad-output/implementation-artifacts/sprint-status.yaml](./_bmad-output/implementation-artifacts/sprint-status.yaml)** - Sprint 进度与故事状态跟踪
- **[_bmad-output/implementation-artifacts/1-1-project-scaffold-initialization.md](./_bmad-output/implementation-artifacts/1-1-project-scaffold-initialization.md)** - Story 1-1：项目脚手架初始化
- **[_bmad-output/implementation-artifacts/1-2-pydantic-request-response-models.md](./_bmad-output/implementation-artifacts/1-2-pydantic-request-response-models.md)** - Story 1-2：Pydantic 请求响应模型定义
- **[_bmad-output/implementation-artifacts/1-3-fastapi-lifespan-http-client.md](./_bmad-output/implementation-artifacts/1-3-fastapi-lifespan-http-client.md)** - Story 1-3：FastAPI 生命周期 HTTP 客户端
- **[_bmad-output/implementation-artifacts/1-4-chat-route-global-exception-handler.md](./_bmad-output/implementation-artifacts/1-4-chat-route-global-exception-handler.md)** - Story 1-4：聊天路由与全局异常处理
- **[_bmad-output/implementation-artifacts/2-1-session-storage-history-persistence.md](./_bmad-output/implementation-artifacts/2-1-session-storage-history-persistence.md)** - Story 2-1：会话存储与历史持久化
- **[_bmad-output/implementation-artifacts/2-2-new-session-init-hook.md](./_bmad-output/implementation-artifacts/2-2-new-session-init-hook.md)** - Story 2-2：新会话初始化钩子
- **[_bmad-output/implementation-artifacts/2-3-agent-loop-full-implementation.md](./_bmad-output/implementation-artifacts/2-3-agent-loop-full-implementation.md)** - Story 2-3：Agent 循环完整实现
- **[_bmad-output/implementation-artifacts/3-1-tools-full-implementation.md](./_bmad-output/implementation-artifacts/3-1-tools-full-implementation.md)** - Story 3-1：所有租房工具函数实现
- **[_bmad-output/implementation-artifacts/4-2-log-event-structured-logging.md](./_bmad-output/implementation-artifacts/4-2-log-event-structured-logging.md)** - Story 4-2：结构化日志 log_event 实现
