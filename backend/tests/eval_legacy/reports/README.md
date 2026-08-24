# Eval V1 报告索引

本目录把“当前可比较的 Baseline”“综合运行结果”和“早期模块报告”分开保存，避免报告散落
在不同测试模块中。

## 目录职责

- `baselines/`：带题集摘要、Provider、Model 等身份信息的机器可比较基线。
- `comprehensive/`：2026-08-23 综合 Eval 的逐轮输出；每轮保留 `report.json` 和
  `report.md`。
- `historical/runtime/`：2026-08-06 至 08-09 的 Runtime 初代报告。
- `historical/memory/`：2026-08-12 的 Memory 独立测评报告。
- `historical/skill_learning/`：2026-08-18 的 Skill Learning 独立测评报告。

## 综合评测演进

| 报告 | 样本结果 | 说明 |
| --- | ---: | --- |
| `20260823_073914_431641` | 11/15（73.3%） | 首轮综合 Smoke，暴露 Task 与 Memory 断言问题 |
| `20260823_080335_718449` | 4/12（33.3%） | 问题样本定向复测，题集不同，不可与首轮直接比较 |
| `20260823_081030_281885` | 5/12（41.7%） | 第一轮修正后复测 |
| `20260823_081526_968835` | 10/12（83.3%） | Task 规则与 Memory 语义断言继续收口 |
| `20260823_081807_566853` | 43/45（95.6%） | 三套 Smoke、每条三次 |
| `20260823_091702_628798` | 57/68（83.8%） | 扩大题集后的真实 Bad Case 基线 |
| `20260823_112858_055392` | 192/204（94.1%） | 完整 Regression 三次的正式阶段结果 |
| `20260823_125215_041071` | 25/33 | 11 条困难样本诊断集，不是全量 Baseline |
| `20260823_131617_888097` | 3/3 | learning-05a 单场景修复确认 |

上表中的分母、场景集合和场景定义摘要并不总相同。只有 `report.json` 的 Provider、Model、
Suite、Tier、场景集合与 digest 全部一致时，Baseline 比较才有统计意义。

更完整的优化故事见
[docs/eval-records/agent-eval-optimization-story.md](../../../../docs/eval-records/agent-eval-optimization-story.md)。
