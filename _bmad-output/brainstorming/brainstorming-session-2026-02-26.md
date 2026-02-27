---
stepsCompleted: [1, 2, 3, 4]
inputDocuments: ['docs/task.md', 'docs/interface.md', 'docs/interface_simulate.md', '_bmad-output/project-context.md']
session_topic: '兼容Anthropic Skills的租房AI Agent架构设计——CLI工具封装与Agent Loop构建'
session_goals: '1. 将确定性的租房API调用流程封装成CLI工具；2. 通过skills机制将CLI工具暴露给大模型；3. 构建Agent Loop动态调用接口或CLI工具；4. 整体架构兼容Anthropic skills格式'
selected_approach: 'ai-recommended'
techniques_used: ['First Principles Thinking', 'Morphological Analysis', 'Constraint Mapping']
ideas_generated: 12
session_active: false
workflow_completed: true
context_file: '_bmad-output/project-context.md'
---

# Brainstorming Session Results

**Facilitator:** LJW
**Date:** 2026-02-26

## Session Overview

**Topic:** 兼容Anthropic Skills的租房AI Agent架构设计——CLI工具封装与Agent Loop构建

**Goals:**
1. 将确定性的租房API调用流程封装成CLI工具
2. 通过skills机制将CLI工具暴露给大模型
3. 构建Agent Loop动态调用接口或CLI工具
4. 整体架构兼容Anthropic skills格式

### Context Guidance

基于项目文档分析：
- 技术栈：Python 3.11 + FastAPI + qwen3-32b（OpenAI兼容接口）
- 外部API：15个租房仿真接口（房源查询/地标/租赁操作）
- 核心约束：时间片限制、Token效率、5秒非模型处理上限
- 竞赛场景：单轮/多轮对话、房源筛选推荐、多维度分析

---

## Technique Selection

**方式：** AI 推荐技术序列
**分析上下文：** 技术架构设计 + 竞赛约束导航

**推荐技术：**
- **First Principles Thinking（第一性原理）：** 剥离隐性假设，从竞赛评测本质重构架构基础
- **Morphological Analysis（形态学分析）：** 系统枚举6个设计维度的所有参数组合，找到最优交叉点
- **Constraint Mapping（约束地图）：** 将9项竞赛约束逐一与架构方案碰撞，过滤出可落地方案

---

## Technique Execution Results

### 阶段一：First Principles Thinking

通过拆解"意图 vs 执行"的本质边界，建立了以下核心洞察：

**[架构 #1]**: 意图映射原则（Intent-Mapped Tools）
_Concept_: 工具粒度 = 用户意图类型（6-8个），而非 API 端点（15个）。意图类型是天然的工具数量上界，防止工具爆炸。
_Novelty_: 把 15 个 API 压缩到 6-8 个意图工具，模型只需理解"我要找房"而不是"先查地标再查附近"。

**[架构 #2]**: 两段式意图协议（Two-Phase Intent Protocol）
_Concept_: 模型先调用 `extract_intent` 工具将自然语言转成标准化意图对象（JSON），再用意图对象调用实际查询工具。
_Novelty_: 将"理解"和"执行"解耦为两个独立可测试单元，意图提取结果可被缓存复用，复杂多轮不需反复提取同一维度。

**[架构 #3]**: 会话结果集游标（Session Result Cursor）
_Concept_: 每次查询结果同时写入会话级"当前结果集"（带序号索引），工具层维护此游标状态。
_Novelty_: 解决"那个""刚才第二套"的指代消解，让 `filter_current_results` 在已有结果上叠加筛选，避免重复调用 API。

**[架构 #4]**: 意图状态机（Intent State Machine）
_Concept_: 会话状态维护结构化"当前意图状态"对象 `{district, price_range, room_type, ...}`，每轮对话产生 PATCH 操作而非全新查询。
_Novelty_: 把多轮意图积累变成可审计的显式状态，模型只需理解"这次用户改了什么"，不需每次重新提取全部意图。

**[架构 #5]**: 被动偏好捕获（Passive Preference Extraction）
_Concept_: 每轮（包括纯聊天轮）运行轻量偏好提取器，把负面描述、情绪表达转换为正向偏好写入意图状态机，不触发 API 调用。
_Novelty_: 把"吐槽轮"从 no-op 变成"隐性偏好采集轮"，解决竞赛多轮用例中"前几轮铺垫、后几轮爆发"的典型模式。

**[架构 #6]**: TDD 驱动的工具边界收敛（Test-Driven Tool Boundary Refinement）
_Concept_: 先以最小可行工具集（7-8个）上线，通过竞赛公开测试用例的失分点识别"意图盲区"，再针对性补充工具或扩展参数。
_Novelty_: 用竞赛评测系统作为天然"意图覆盖率测试仪"，每次打榜相当于一次回归测试，失分 Case 直接暴露工具缺口。

---

### 阶段二：Morphological Analysis

**形态学矩阵（6维度 × 3选项）：**

| 维度 | 选项 A | 选项 B | 选项 C | **推荐** |
|------|--------|--------|--------|----------|
| ①工具粒度 | 原子工具×15 | 意图工具×7 | 两层（内部原子+外部意图） | **C** |
| ②工具实现形式 | Python函数（内嵌） | 独立CLI脚本 | 混合（函数+CLI入口） | **C** |
| ③会话状态存储 | 只存消息历史 | +结构化意图对象 | +结果集游标+意图对象 | **B（先），C（后）** |
| ④Skills暴露格式 | OpenAI格式 | Anthropic格式 | 两者兼容适配层 | **C** |
| ⑤Loop策略 | 单次调用 | 标准ReAct（≤10次） | 分阶段Pipeline | **B（先），C（后）** |
| ⑥偏好捕获时机 | 仅查询轮 | 每轮提取 | 首轮特殊+增量更新 | **C** |

**[架构 #7]**: 双入口 CLI 设计（Dual-Entry CLI Pattern）
_Concept_: 每个工具同时提供 Python 函数入口（TDD友好）和 CLI 入口（Anthropic Skills兼容），共享同一套业务逻辑。
_Novelty_: 一份代码两种调用方式，既保留测试友好性，又满足 Skills 要求的进程隔离。

**[架构 #8]**: 三阶段显式 Pipeline
_Concept_: Agent Loop 强制分为三阶段，每阶段有独立系统提示和工具子集：理解→搜索→推荐，防止模型在推荐阶段又去重新搜索。
_Novelty_: 把不确定的自由 ReAct 变成有约束的确定性流程，Token 消耗可预测，时间片可控（固定3-5次模型调用）。

---

### 阶段三：Constraint Mapping

**约束地图（9项竞赛约束 × 架构应对）：**

| 约束 | 威胁等级 | 架构应对 | 状态 |
|------|----------|----------|------|
| C1 非模型处理<5秒 | 🟡 中等 | 并发工具调用 | ✅ 解决 |
| C2/C3 时间片300片 | 🔴 高危 | 动态上下文注入 | ✅ 解决 |
| C4 JSON格式强制 | 🔴 高危 | 输出格式守卫 | ✅ 解决 |
| C5 必须调API操作 | 🟡 中等 | execute_action工具 | ✅ 覆盖 |
| C6 X-User-ID隔离 | 🟡 中等 | Session init钩子 | ✅ 覆盖 |
| C7 禁止外部模型 | ⚫ 即死 | 架构层无需处理 | ✅ 规避 |
| C8 Token消耗排名 | 🟡 中等 | 精简提示+动态注入 | ✅ 解决 |
| C9 系统提示过长 | 🟡 中等 | 800 Token硬上限 | ✅ 解决 |
| C10 分页漏查 | 🔴 高危 | 自适应翻页 | ✅ 解决 |

**[约束洞察 #9]**: 并发工具调用（Concurrent Tool Execution）
_Concept_: 当模型单次返回多个独立 `tool_calls` 时，用 `asyncio.gather` 并发执行，把 N×200ms 压缩到 200ms。
_Novelty_: qwen3-32b 支持单次返回多个工具调用，但大多数实现只串行处理——并发执行是免费的时间片节省。

**[约束洞察 #10]**: 动态上下文注入（Dynamic Context Injection）
_Concept_: 系统提示设 800 Token 硬上限，工具使用示例、API字段说明等按需在相关轮次注入，而非全部塞进系统提示。
_Novelty_: 平均每次调用节省 1-2k Token，在 300 片预算内多跑 15-20% 的用例。

**[约束洞察 #11]**: 输出格式守卫（Output Format Guard）
_Concept_: 不让模型自由生成最终响应，用专门的"格式化工具"组装输出——模型只负责 `message` 文本和 `house_id` 列表，代码负责 `json.dumps`。
_Novelty_: 把高风险的"模型遵从性"问题转换为零风险的"代码确定性"问题，彻底消除 JSON 格式错误失分。

**[约束洞察 #12]**: 智能分页策略（Adaptive Pagination）
_Concept_: CLI 工具内实现自适应翻页——首次查询后若 `total > page_size`，自动并发拉取剩余页（上限5页/50条），返回完整结果集给模型。
_Novelty_: 把"模型是否记得翻页"的不确定性，变成"CLI工具自动翻页"的确定性，典型的"不确定性从AI层转移到CLI层"。

---

## Idea Organization and Prioritization

### 主题归类

**主题一：工具架构设计** — #1 意图映射原则、#2 两段式意图协议、#7 双入口CLI设计
**主题二：会话状态管理** — #3 会话结果集游标、#4 意图状态机、#5 被动偏好捕获
**主题三：Agent Loop优化** — #6 TDD驱动边界收敛、#8 三阶段Pipeline、#9 并发工具调用
**主题四：竞赛约束应对** — #10 动态上下文注入、#11 输出格式守卫、#12 智能分页策略

### 优先级矩阵

| 优先级 | 想法 | 影响力 | 难度 | 实现时机 |
|--------|------|--------|------|----------|
| 🔴 P0 | #7 双入口CLI设计 | 架构基础 | 低 | MVP第一天 |
| 🔴 P0 | #1 意图映射原则 | 核心框架 | 低 | MVP第一天 |
| 🔴 P0 | #11 输出格式守卫 | 直接防失分 | 极低 | MVP第一天 |
| 🔴 P0 | #12 智能分页策略 | 防漏查失分 | 低 | MVP第一天 |
| 🟡 P1 | #4 意图状态机（简化版） | 多轮连贯性 | 中 | MVP第二天 |
| 🟡 P1 | #10 动态上下文注入 | Token节省 | 中 | MVP第二天 |
| 🟡 P1 | #9 并发工具调用 | 性能优化 | 低 | MVP第二天 |
| 🟢 P2 | #3 会话结果集游标 | 复杂多轮 | 中 | TDD迭代后 |
| 🟢 P2 | #5 被动偏好捕获 | 多轮高分 | 中 | TDD迭代后 |
| 🔵 P3 | #8 三阶段Pipeline | 高可控性 | 高 | 时间允许 |
| 🔵 P3 | #2 两段式意图协议 | 可测试性 | 中 | 时间允许 |

### Action Plans — MVP 实现路径

**P0 行动计划（第一天）：**
1. 创建 `tools/` 目录，按双入口CLI模式实现 6 个意图工具
2. 在 `agent.py` 中实现标准 ReAct Loop + 输出格式守卫
3. 每个查询工具内置自适应翻页（max 5页）
4. 编写每个工具的单元测试（Python函数入口直接 import 测试）

**P1 行动计划（第二天）：**
1. 在 `session.py` 中添加结构化意图状态对象（简化版状态机）
2. 系统提示控制在 800 Token 以内，提取工具说明到动态注入层
3. Agent Loop 中对多个独立 tool_calls 使用 `asyncio.gather` 并发执行

**TDD 迭代计划（打榜后）：**
- 失分 Case 类型 → 对应补充方案
  - "第N套"指代失败 → 实现 #3 会话结果集游标
  - "前面说过的需求"丢失 → 实现 #5 被动偏好捕获
  - 时间片超出预算 → 实现 #8 三阶段 Pipeline
  - Token消耗过高 → 强化 #10 动态上下文注入

---

## Session Summary and Insights

**Key Achievements:**
- 产出 12 个架构洞察，覆盖工具设计、状态管理、Loop优化、约束应对四大主题
- 建立了完整的形态学矩阵（6维度），推导出最优参数组合
- 完成全部 9 项竞赛约束的架构应对映射，无遗漏硬约束

**Session Reflections:**
- 核心突破：把"API端点粒度"改为"用户意图粒度"，工具数量从15降到7-8，防止参数爆炸
- 关键洞察：竞赛评测系统本身就是最好的 TDD 测试套件，MVP先行、失分驱动迭代是最务实的策略
- 架构原则：把不确定性从 AI 层转移到 CLI 层（翻页、格式、偏好提取），是贯穿全局的设计哲学

Last Updated: 2026-02-26
