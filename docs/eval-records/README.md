# Vesta Eval 记录

> 集中的评测记录目录（2026-08-18 建立）。
> 本目录收录每个模块做过的测试、真实模型 Live Eval 结果与各阶段 Bad Case 分析。
> 代码在 `backend/tests/`；Eval 基建：
> - Agent Runtime / Skill Learning → `backend/tests/eval/`
> - 长期记忆 → `backend/tests/memory_eval/`
> - 综合入口 → `backend/tests/eval/run_suite.py`
> 原始时间戳报告保留在各 `reports/` 子目录。

## 目录

| 文件 | 内容 | 来源 |
| --- | --- | --- |
| `runtime-agent-evaluation.md` | Agent Runtime 通用测评（场景库/基线/压缩稳定性）+ 长期记忆测评结果 | 原根目录 `evaluation.md` |
| `agent-eval-optimization-story.md` | 2026-08-23 综合 Eval 框架、真实 Bad Case、优化过程、结果与诚实边界 | 本轮综合评测收口 |
| `memory-evaluation-design.md` | 长期记忆测评设计（确定性不变量 + 真实模型语义测评分层、场景结构、运行方式） | 原 `docs/memory-evaluation.md` |
| `skill-learning-eval-history.md` | Skill Learning V1 各阶段 Bad Case、Eval 指标与提升历史（阶段一~四） | 原根目录 `skill-learning-eval-history.md` |
| `backend/tests/eval/reports/` | Agent Runtime / Skill Learning 的 Live Eval 原始报告（时间戳） | 代码库 |
| `backend/tests/memory_eval/reports/` | 长期记忆 Live Eval 原始报告 | 代码库 |

## Agent 综合评测 V1

综合入口不替换现有 Harness，而是把 Core、Memory、Skill Learning 转换为统一的
`EvalSampleRecord`。三套评测继续使用自己的环境、断言和 Judge，但共享以下输出口径：

- 样本通过率与多次运行的稳定通过率；
- Main Agent、Context Summary、Memory Reflection、Maintenance 和 Provider Total；
- Cached / Uncached Input、可计费 Token、模型调用次数与耗时；
- 单样本 `sample.json`、Agent 类评测的 `trace.json`、综合 `report.json` 和 `report.md`；
- 同 Provider、Model、Suite、Tier、场景集合和场景定义摘要下的 Baseline 比较。

Smoke 场景只覆盖关键路径，Regression 包含全部非 Manual 场景。真实模型评测会产生 API
成本，必须显式运行，不进入普通 `pytest`：

```bash
cd backend

# Core Smoke
.venv/bin/python -m tests.eval.run_suite \
  --suite core --tier smoke --runs 1 --print

# 三套综合 Smoke；建议建立正式基线时每条运行 3 次
.venv/bin/python -m tests.eval.run_suite \
  --suite core --suite memory --suite learning \
  --tier smoke --runs 3 \
  --save-baseline tests/eval/reports/baselines/deepseek-smoke.json

# 使用相同模型和完全相同题集比较
.venv/bin/python -m tests.eval.run_suite \
  --suite core --suite memory --suite learning \
  --tier smoke --runs 3 \
  --baseline tests/eval/reports/baselines/deepseek-smoke.json
```

Baseline V1 将安全场景失败、原本稳定通过场景退化作为阻断项；平均可计费 Token 增长超过
20% 只产生警告。不同模型、不同题集或场景定义发生变化时拒绝直接比较，避免生成没有意义的
升降结论。

RunManager / Recovery、Automation、MCP、Computer 和真实审批浮窗目前继续由离线集成测试与
macOS 手动 E2E 负责。它们不伪装成普通 Live 场景，也不会在 CI 中自动控制电脑或连接外部
MCP；后续应以独立 Integration / Manual Suite 接入同一 Sample Record。

> 合并说明：根目录 `evaluation.md`、`skill-learning-eval-history.md` 与
> `docs/memory-evaluation.md` 均通过 `git mv` 移入本目录（保留 Git 历史），
> 原位置文件已删除。

---

## 模块测试记录总表（截至 2026-08-18 · 全量 `pytest` 545 passed）

> 离线确定性单测（Fake Model）覆盖「系统会不会写坏」；真实模型 Live Eval 覆盖
> 「模型记得好不好 / 判断对不对」。两类结果分开，不混成一个通过率。

| 模块 | 测试文件（用例数） | 覆盖点 | 离线结果 | 真实模型 Live Eval | 分析 / 结论 |
| --- | --- | --- | --- | --- | --- |
| Agent Runtime | `test_agent_runtime.py` (26)、`test_agent_events.py` (5) | 主循环、AgentEvent、停止原因、Run 生命周期 | ✅ 全过 | 30 场景 → **86.7%** (26/30) | Task 状态正确率 100%；压缩场景经 reasoning 摘要适配后稳定 |
| 工具层 | `test_tools.py` (17)、`test_tool_extras.py` (10)、`test_tool_permissions.py` (9)、`test_tool_hooks.py` (6)、`test_task_tools.py` (27) | 内置工具、三档权限、审批门、Hook 生命周期、任务工具 | ✅ 全过 | safety 组通过率 100%（修复后） | 安全拒绝/审批链路稳定 |
| Task | `test_task_store.py` (35) | Task 状态机、store、写入一致性 | ✅ 全过 | — | 状态机稳定基线 |
| Context | `test_context_blocks.py` (11)、`test_context_budget.py` (10)、`test_context_capabilities.py` (11)、`test_context_config.py` (9)、`test_context_history.py` (7)、`test_context_summary.py` (12)、`test_context_tool_reducer.py` (10)、`test_summarizer_reasoning.py` (6)、`test_token_estimator.py` (14) | 两层压缩、预算、摘要、reasoning 模型适配、Token 估算 | ✅ 全过 | 压缩场景 runs1 100%、runs3 77.8% | 摘要对 deepseek 关闭 thinking + 硬性有效性校验后主链路稳定 |
| 模型适配 | `test_model_adapters.py` (5) | provider 适配、请求构造 | ✅ 全过 | — | — |
| 会话 / 持久化 | `test_chat_sessions.py` (11)、`test_checkpoint_store.py` (6)、`test_conversation_store.py` (4)、`test_trace_store.py` (5) | 会话、Checkpoint、Trace 存储 | ✅ 全过 | — | — |
| MCP | `test_mcp.py` (11) | MCP 接入 | ✅ 全过 | — | — |
| 权限规则 / 搜索 | `test_permission_rules.py` (21)、`test_search_providers.py` (10) | 权限规则持久化、Bing 搜索解析 | ✅ 全过 | — | — |
| Skills Runtime V2 | `test_skills.py` (43)、`test_skills_eval.py` (4) | 激活、Progressive Disclosure、资源读取、压缩存活 | ✅ 全过 | skill 组 15 场景（随 Runtime 基线） | survives_compaction 已覆盖 |
| Skill Learning V1 | `test_skill_learning.py` (43)、`test_skill_learning_eval.py` (9)、`test_learning10_realistic.py` (14) | Mining→Distill→Human Gate→Discover；learning-10 20-Task 增强（trace steps / evidence / 阈值 / pitfall 同义组） | ✅ 全过（545 内含） | 旧 9 场景 → **87%** (26/30)；learning-10 20-Task → 上一轮 **0/3** → 本轮 **3/3 PASS** | CREATE/UPDATE/NONE 语义已钉死为 task family；详见 `skill-learning-eval-history.md` |
| Memory | `test_memory_system.py` (45)、`test_memory_reflection.py` (14)、`test_memory_maintenance.py` (10)、`test_memory_eval.py` (4) | 分层（Core/Task/Ordinary）、Reflection、Maintenance、跨会话召回 | ✅ 全过 | 10 场景 × 3 → **81.8%** (27/33) | 召回/回答 100%；UPDATE 漏判（memory-05）待真实重跑确认 |
| Trace Selector | `test_trace_selector.py` (12) | 锚点区间选择、去重、跨 Run | ✅ 全过 | — | 与生产 `TaskTraceSelector` 共用 |
| Eval Harness | `test_harness.py` (13) | 通用场景 harness 自身 | ✅ 全过 | — | — |

---

## 真实模型 Live Eval 汇总

| 模块 | 场景 / 样本 | 通过率 | 关键报告 |
| --- | --- | --- | --- |
| Agent Runtime 通用 | 30 场景 × 1 | **86.7%** (26/30) | `backend/tests/eval/reports/baseline_20260806_v2_86.7.md` |
| 长期记忆 | 10 场景 × 3（33 阶段） | **81.8%** (27/33) | `backend/tests/memory_eval/reports/memory_report_20260812_*.md` |
| Skill Learning（旧 9 场景） | 10 场景 × 3 | **87%** (26/30) | `backend/tests/eval/reports/skill_learning_live_20260818c.md` |
| Skill Learning learning-10（20-Task） | 1 场景 × 3 | 上一轮 **0/3** → 本轮 **100%** (3/3) | `backend/tests/eval/reports/skill_learning_live_20260818.md` |

> 报告文件名的日期后缀代表生成时间；同一模块存在多份报告时，最新一份在
> `git log` / 文件 mtime 中可见，历史报告保留原始失败样本，不覆盖不隐藏。

---

## 结论速览

- **系统确定性链路稳定**：离线全量 545 passed；Task 状态机、权限/审批、Trace/Evidence、
  Skill 激活与 Learning 管线均为确定性行为。
- **真实模型最稳定**：Agent Runtime 核心（Task/工具/安全）、Memory 召回/回答、Skill
  Learning Pattern Mining（precision/recall≈1.00）。
- **真实模型难点**：Memory Reflection 的 UPDATE 稳定漏判；Skill Learning 的
  CREATE/UPDATE 边界（已通过 Distillation 语义修正为 task family，learning-10 3/3 PASS）。
- 每阶段失败样本都如实保留在报告中，不隐藏失败。
