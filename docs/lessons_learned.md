# $150买来的 AI Coding 经验教训

**摘要**：部门举办了个[AI Agent编程挑战赛](task.md)，时间很短（1周）。我为了深度实践AI Coding，向OpenClaw的作者学习，在一周内花费了**$150**，对Cursor + Claude Opus 4.6做了深度体验，5天时间，完全以**Agent Mode运行**，提交了**156个commit**，在项目中构建了完整的**本地闭环**流程，1.3万行代码（测试+流程），还有文档若干。但结果却不尽如人意，AI代码在竞赛中排名后10%，过程中遇到了XX、XX、XX、XX等等问题，不过这也让我对AI编码有了一个全新的认知。

## 为什么我要做这个事情

效仿OpenClaw作者Peter以及OpenAI团队的实践，两个案例均是在短短的几个月内，构筑了几十万行质量达到生产水平的代码，如果按华为产品开发端到端500人月的工作量来算，这已经将软件生产效率提升了100倍以上了。


因此，我希望通过实践，走他们走过的路，也期望能收获一些独特的感悟。

* [OpenAI harness-engineering](https://openai.com/zh-Hans-CN/index/harness-engineering/)：OpenAI 团队通过完全由 Codex 智能体编写代码、人类只做架构与规则设计的方式，仅用少量工程师、极短时间就完成百万行级别的可用软件项目，重新定义了 AI 时代工程师的角色与工程研发范式。
* [The creator of OpenClaw: "I ship code I don't read"](https://www.youtube.com/watch?v=8lF7HmQ_RgY&t=67s)：Peter 对 AI 编码的观点:价值在系统设计、验证和决策，不在手写实现；企业要改流程和角色才能用好 AI
  * **角色**：自己做架构师、定方向，不逐行看 AI 写的“管道代码”；多 AI 并行，用对话规划代替传统 PR。
  * **质量**：靠编译 → 测试 → 运行的闭环验证，少依赖人工逐行审；多用 CLI，少用 MCP。
  * **行业**：写代码成本下降，PR/Code Review/CI 会重构；企业可减约 30% 人力，但需要更多懂系统设计、能动性强的资深工程师。
  * **新人**：重点学系统设计（看开源、问 AI），不必纠结手写每一行；新人没包袱，更容易用 AI 玩出新用法。
  

## 我的账单 & 代码成果

### 账单

![img.png](img.png)
![img_1.png](img_1.png)
![img_2.png](img_2.png)

依次为：
* Cursor Pro, Pro+订阅：$80
* Claude Opus/Sonnet $41.63
* PoloAPI 模型聚合平台：$10
* 阿里云 Qwen3-32B API：￥60

## 项目在做什么（不是关键，建议跳过）

### 问题

![img_5.png](img_5.png)

待解决问题总结（约 200 字）：
* 需要开发一个租房 AI Agent，在比赛环境中同时满足「判题接口」和「仿真数据源」的约定，并正确完成评测用例。
* 判题侧：Agent 需实现 POST /api/v1/chat，接收 session_id、message、model_ip，仅能通过判题器提供的模型接口（如 qwen3-32b）进行推理；完成房源查询时，response 必须是合法 JSON 字符串，包含 message 和 houses（房源 ID 列表），不能是纯自然语言。
* 仿真侧：调用房源相关接口必须带请求头 X-User-ID（平台注册工号）；新会话需调用房源重置接口以保证数据可复现；租房/退租/下架必须调用对应 API 才视为生效。
* 目标：在 300 时间片内按顺序跑完评测用例，在单用例 5 秒（不含模型调用时间）内返回结果，通过聊天、单轮、多轮等用例拿分，并在同分时尽量少耗 token 以提高排名。

### 架构

一言以概之，写了个最简单的Agent，为了实现OpenClaw作者口中的**闭环**，特意搭建了一个本地的测试仿真器，通过严格的用例验证，确保本地测试仿真与内网API完全对齐

![img_6.png](img_6.png)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     Judge / Test Client (external)                              │
│                    POST /api/v1/chat (model_ip, session_id, message)            │
└───────────────────────────────────────────┬─────────────────────────────────────┘
                                            │
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         Main Service (project root)                             │
│  ┌─────────────┐                                                                │
│  │   main.py   │  FastAPI entry · Session management · Lifecycle                │
│  │             │  - lifespan: create httpx.AsyncClient (RENTAL_API_BASE)        │
│  │             │  - POST /api/v1/chat → session init / history → run_agent()    │
│  │             │  - Globals: sessions, session_stats, session_preferences       │
│  └──────┬──────┘                                                                │
│         │                                                                       │
│         │  history, model_ip, client, session_id, session_prefs                 │
│         ▼                                                                       │
│  ┌─────────────┐     ┌─────────────────────────────────────────────────────────┐│
│  │  agent.py   │────▶│ tools.py                                                ││
│  │             │     │ - UserPreferences, AREA_TO_DISTRICT, LANDMARK_NAMES     ││
│  │ LLM loop    │     │ - init_houses, get_all_houses_for_debug,                ││
│  │ - OpenAI    │     │   get_all_landmarks_for_debug                           ││
│  │   (model_ip │     │ - update_preferences, get_house_detail,                 ││
│  │   :8888)    │     │   execute_action, get_house_listings                    ││
│  │ - TOOLS     │     │ - All requests go through client to rental API          ││
│  │ - dispatch  │     └───────────────────────┬─────────────────────────────────┘│
│  └──────┬──────┘                             │                                  │
│         │                                    │ httpx.AsyncClient                │
│         │  log_event                         │ (RENTAL_API_BASE / Mock)         │
│         ▼                                    ▼                                  │
│  ┌─────────────┐     ┌─────────────────────────────────────────────────────────┐│
│  │  logger.py  │     │ Rental API (real or Mock)                               ││
│  │ jsonl per   │     │ - Real: RENTAL_API_BASE (e.g. http://7.225.29.223:8080) ││
│  │ session     │     │ - Test: test-simulator Mock Rental (:8080)              ││
│  └─────────────┘     └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────┘

         │ LLM requests (model_ip:8888)
         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     test-simulator (evaluation / local integration)             │
│  ┌─────────────────┐   ┌─────────────────┐  ┌─────────────────┐                 │
│  │ model_proxy.py  │   │ mock_rental.py  │  │  dashboard.py   │                 │
│  │ :8888           │   │ :8080           │  │  :8877          │                 │
│  │ Proxy /v1/chat/ │   │ 15 rental API   │  │  Interaction    │                 │
│  │ completions →   │   │ endpoints +     │  │  visualization  │                 │
│  │ real LLM        │   │ fixture data    │  │                 │                 │
│  └─────────────────┘   │ _reload_fixture │  └─────────────────┘                 │
│         ▲              └─────────────────┘                                      │
│         │                       ▲                                               │
│  ┌──────┴───────────────────────┴──────┐                                        │
│  │ main.py (simulator)                 │ config.yaml,test_cases.yaml,fixtures   │
│  │ - Start three services (proxy / mock / dashboard)                            │
│  │ - Optional: run_cases_parallel() → runner                                    │
│  └──────┬──────────────────────────────┘                                        │
│         │                                                                       │
│         ▼                                                                       │
│  ┌─────────────────┐  ┌─────────────────┐                                       │
│  │   runner.py     │  │   config.py     │                                       │
│  │ - send_message  │  │ - SimulatorConfig, TestCase, ExpectRules                │ 
│  │   → Agent       │  │ - TokenCounter, CaseResult, RoundDetail                 │ 
│  │   /api/v1/chat  │  │ - load_config, load_fixtures, load_test_cases           │
│  │ - Assertion     │  └─────────────────┘                                       │
│  │   engine        │                                                            │
│  │   (ASSERTION_   │                                                            │
│  │    RULES)       │                                                            │
│  │ - Report gen    │                                                            │
│  └─────────────────┘                                                            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 成果

128个测试用例，qwen-32b实现正确提参XX个，token总消耗XX

## 我的构思

下面详细展示一下我的整个AI Coding的全过程

### 工具选型

* Claude 订阅：很容易被封号，需要有美国的家庭VPS做流量转发才可以使用，太麻烦了，后续配通再考虑
* Claude + PoloAPI（模型聚合平台）：通过配置Claude运行在API模式，对接三方API平台的Claude Opus/ Sonnet大模型，全程很丝滑，但问题就是有点贵，我还没开始干活，光分析代码库，闲聊了一下，就花掉了$10. 备注：这其实也是内网的一个好选择，只要内网有稳定可用的模型API（比如GLM-5，比如期待一下后续会发布的DS-V4），就可以做到稳定高效的编码
* 【最终选择】Cursor + Claude模型：Cursor订阅已经5个月了，陆陆续续一直在使用，账号一直没有被封禁，只要VPN OK，就可以稳定连接SOTA模型进行编码；Agent模式也兼容 Anthropic Skills，具备CLI执行，端到端闭环能力，一路用下来能够满足我的初始使用要求

### 工程化AI编码实践，BMAD-Method

#### Agent Engineering vs Vibe Coding

这里我想讨论一下我理解的，这一代Agent Engineering与Vibe Coding的核心区别：
* Vibe Coding：人类把单点需求传递给LLM，让LLM帮你完成需求/测试用例的开发；联调验证等工作仍由人类完成，当系统的规模膨胀后，AI对软件的理解依赖人类传递的上下文，无法自主完成工作
* Agent Engineering：文章最开头的两篇文章里都不约而同的提到，软件要以便于Agent理解的方式组织与构建，这样AI才能高效的理解数十万行的软件代码，实现高效的开发与任务闭环，因此，本次开发过程中，重点实践了通过Agent Engineering的方式进行开发。这里再重复一下前文关于AI Coding中，人类扮演的角色总结：
  * 架构师视角：定义目标与意图，不写实现
  * 设计环境与规则，让 AI 可以检测与验证自己的产出（端到端闭环测试 & CI & Lint）
  * 给 AI 提供 “地图”，而不是长篇手册：把知识、文档、设计、计划全部放进代码仓库，AI 看不到的东西 = 不存在。
  * 处理瓶颈与反馈，持续提升 AI 能力：当AI处理出现偏差时，分析软件工程上的短板，补充文档、测试、工具、规则
  * 做最终判断与质量守门人

#### [BMAD-Method工具](https://docs.bmad-method.org/tutorials/getting-started/)

这是一套符合Agent Engineering工程理念的一个工具，先介绍一下他是什么：

官方介绍，核心要点：一个AI-driven development的框架，定义了一套工作流，可以规范AI编码的开发过程
```txt
The BMad Method (Build More Architect Dreams) is an AI-driven development framework module within the BMad Method Ecosystem that helps you build software through the whole process from ideation and planning all the way through agentic implementation. It provides specialized AI agents, guided workflows, and intelligent planning that adapts to your project’s complexity, whether you’re fixing a bug or building an enterprise platform.

If you’re comfortable working with AI coding assistants like Claude, Cursor, or GitHub Copilot, you’re ready to get started.
```

看官方介绍还是有点抽象，那么再看一个图

![Workflow_Map_BMAD_Method.png](Workflow_Map_BMAD_Method.png) 

```c++
# TODO: 录个屏，展示一下头脑风暴的过程
```

总结一下：
* 从概念设计 -> 架构设计 -> 迭代计划拆解 -> 实施 & 验证；这个工具是敏捷迭代思想的现实映射
* 它是一个插件（本质上是一套Prompt & Skill），能够被cursor, claude, codex, opencode等编码Agent无缝集成
* 在使用时，可以按需调用不同的工作流，实现你想要的事情

### 本地闭环能力构筑

在本次比赛中，测试环境有两个，工具调用服务器与大模型，均部署在内网。那么，为了让AI的代码在本地可运行，搭建了工具调用Mock服务器 & 大模型Proxy & 测试用例运行判题器。

在后续的本地调测中，测试用例运行判题器起到了非常重要的作用，这可以作为最终人类验收AI成果的依据，为方便人类检阅测试结果，同时方便AI分析测试结果，我还为用例判题器添加了网页展示与关键日志存储，人类查看网页，AI根据日志进行迭代

最终，我可以这样让AI干活：
```c++
# TODO：展示我的端到端闭环prompt
```

### 算法设计与调优

在开发过程中，我发现只要逻辑可被确定性验证的事情，AI能够完成得非常好；整个工程的测试框架、Agent流程，在TDD的配合下，过程非常丝滑

那么剩下待解决的问题只有一个了：如何让不确定的步骤，让“LLM正确提取用户偏好”这件事正确执行。

由于我此前并没有实操构建果一个Agent，我这里如实记录我的一些算法演进：
1. 把工具API的原始参数作为function_call的参数，传递给LLM，让LLM提参执行
2. 分析用例集，构筑一个偏好Adapter，让LLM仅针对Adapter提参，用代码将Adapter转化为工具API调用，解决如，“让模型理解行政区、地标、区域”、“模糊匹配”、“XX左右”等自然语言中存在语义不清的场景
3. 为模型提供few-shot示例
4. 偏好Adapter过大，拆分子Agent，让每个子agent仅负责一部分偏好的提取。（实测下来，这么做的效果很差，模型幻觉率很高）
5. 偏好Adapter过大，拆分子Agent单独处理软偏好，在主Agent已经完成偏好提取的前提下，单独提取“XX最好”、“XX可以吗”等意图
6. 将部分语义空间不大的描述改为规则匹配

# 经验 & 教训

## 确定的可验证的结果是Agentic Engineering的北极星

AI编写测试 -> AI编写代码 -> 测试通过则真的达成了人类的预期吗？

实际上，在实践时，行之有效的e2e验证结果，才是人类检测的重点。比如，在本次实验中，AI兴高采烈的告诉我，所有用例均已通过，结果我看验证报告才发现，AI通过修改了测试用例的检查条件，将用例检查条件放宽，从而通过了测试

## 文档与上下文是AI编码项目成功的关键

我的工程并不复杂，但实践的过程中，我深刻的感受到上下文工程的重要性：

在软件开发的每一步都是一个思维收敛的过程，比如：
* 概念设计阶段，一个目标的实现有N种可能的方案，我要如何选择一种合适的路径，这是一个需要人类参与的过程；这里关键的是，把方案决策，而非讨论过程，通过文档固化下来，作为后续设计的输入，这样AI能取得更好的效果

然而，成也上下文，败也上下文；如何确保在迭代开发过程中，保证 “文档” + “测试用例” + “代码”的一致性与正确性？确保AI不会因为加载了错误的文档，而导致了错误的行为？ -- OpenAI给出了答案，维护专门的Agent，为每个软件模型编写文档，为AI提供理解该模块的正确索引

## 效率真的提升了吗？

答案是明确的：是

1. 在明确的工程脚手架开发领域，AI Coding可以将效率提升5-10X，以前我参加类似的竞赛时，往往前几天都在奋战跟平台联调接口，确保所有接口是符合预期的
2. 在算法迭代阶段，AI Coding可以加速想法的验证，每个想法的验证都可以被快速实施，被运行，被记录，从而加速飞轮的运转效率

一个副作用：人会变得很累

在传统的开发中，编码与调试是单线程的工作；但在AI Coding中，一个任务的下发到完成往往需要5-10分钟，人类的工作状态是并发的。
比如在实践中，我最多并行运行过4个Agent实例，完成：测试报告生成功能添加，算法迭代，工具Mock与内网行为对齐，小Bug修正

# 我的下一步思考

1. 如何以BMAD-Method作为蓝本，对比OpenClaw的文档设计，设计自己的工作流，将Doc作为一等公民，固化下来
2. 能否让一个Agent控制cursor/claude完成“概念设计” -> “架构设计” -> “迭代分解” -> “迭代开发”的全过程，真正做到意图驱动开发？（也许这就是OpenClaw存在的价值）
3. 继续我的Paper-Analysis项目，以Agent Engineering的方式完成重构！这次核心要让AI具备非确定性算法迭代的能力