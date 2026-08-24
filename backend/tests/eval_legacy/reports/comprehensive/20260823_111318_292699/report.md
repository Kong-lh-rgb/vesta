# Vesta Agent 综合评测报告

## 汇总

| 指标 | 值 |
| --- | --- |
| 请求重复次数 | 3 |
| 预期样本数 | 21 |
| 实际样本数 | 21 |
| 样本完整性 | ✅ 完整 |
| 通过数 | 18 |
| 样本通过率 | 85.7% |
| 稳定通过率 | 85.7% |
| 安全场景通过率 | 未知 |
| 平均 Steps | 1.9 |
| 平均模型调用 | 2.3 |
| 平均可计费 Token | 2704 |
| P95 可计费 Token | 5429 |
| 平均缓存命中率 | 59.0% |
| 平均耗时 | 15.5s |

## 运行信息

- Provider / Model：deepseek / deepseek-v4-flash
- Suites：core, memory, learning
- Tier：regression
- Git Commit：35c7a84+working-tree-targeted-v2
- Scenario Digest：e6cf6b052fb710df5e4f91a6df8e71cff72b85e98c1fa80d494eed3329a8d654
- 生成时间：2026-08-23T11:13:18.860950+00:00
- 运行现场：/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-67mxmopy

## 样本完整性

所有稳定性键均包含完整的重复运行样本。

| 稳定性样本 | 期望 Run | 实际 Run | 完整 |
| --- | --- | --- | --- |
| core/skill-03 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/skill-04 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/skill-06 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/skill-15 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| learning/learning-04 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| memory/memory-01/learn (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| memory/memory-01/recall (on) | [1, 2, 3] | [1, 2, 3] | ✅ |

## 分组结果

| Suite / Group | 通过 | 样本 | 通过率 |
| --- | --- | --- | --- |
| core / skill | 9 | 12 | 75.0% |
| learning / learning | 3 | 3 | 100.0% |
| memory / memory | 6 | 6 | 100.0% |

## 分样本

| Suite | 场景 / Phase | Run | 结果 | Stop | Steps | Tools | Main | Summary | Reflection | Total | Chargeable | Cache | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core | skill-03 | 1 | ✅ | final_answer | 3 | 2 | 7135 | 0 | 0 | 7135 | 6111 | 36.4% | 46.3s |
| core | skill-03 | 2 | ✅ | final_answer | 3 | 2 | 6965 | 0 | 0 | 6965 | 5429 | 54.6% | 42.0s |
| core | skill-03 | 3 | ✅ | final_answer | 3 | 2 | 6495 | 0 | 0 | 6495 | 4319 | 76.1% | 39.5s |
| core | skill-04 | 1 | ✅ | final_answer | 3 | 4 | 6889 | 0 | 0 | 6889 | 4713 | 51.5% | 25.3s |
| core | skill-04 | 2 | ✅ | final_answer | 3 | 4 | 5201 | 0 | 0 | 5201 | 3025 | 59.6% | 16.7s |
| core | skill-04 | 3 | ✅ | final_answer | 3 | 4 | 8145 | 0 | 0 | 8145 | 4561 | 70.3% | 29.5s |
| core | skill-06 | 1 | ✅ | final_answer | 2 | 1 | 6804 | 0 | 0 | 6804 | 3732 | 50.5% | 9.3s |
| core | skill-06 | 2 | ✅ | final_answer | 2 | 1 | 6165 | 0 | 0 | 6165 | 661 | 95.5% | 7.0s |
| core | skill-06 | 3 | ✅ | final_answer | 2 | 1 | 6914 | 0 | 0 | 6914 | 1026 | 96.4% | 10.0s |
| core | skill-15 | 1 | ❌ | context_error | 2 | 1 | 970 | 0 | 0 | 970 | 970 | 0.0% | 2.8s |
| core | skill-15 | 2 | ❌ | final_answer | 2 | 1 | 2567 | 0 | 0 | 2567 | 1799 | 39.6% | 9.9s |
| core | skill-15 | 3 | ❌ | context_error | 2 | 1 | 941 | 0 | 0 | 941 | 173 | 92.2% | 2.4s |
| memory | memory-01/learn | 1 | ✅ | final_answer | 1 | 0 | 1223 | 0 | 1340 | 2563 | 2051 | 30.8% | 12.3s |
| memory | memory-01/recall | 1 | ✅ | final_answer | 2 | 1 | 2434 | 0 | 1204 | 3638 | 2102 | 47.9% | 11.8s |
| memory | memory-01/learn | 2 | ✅ | final_answer | 1 | 0 | 1336 | 0 | 1383 | 2719 | 1311 | 83.3% | 10.9s |
| memory | memory-01/recall | 2 | ✅ | final_answer | 2 | 1 | 2438 | 0 | 1132 | 3570 | 2034 | 48.0% | 7.0s |
| memory | memory-01/learn | 3 | ✅ | final_answer | 1 | 0 | 1218 | 0 | 2218 | 3436 | 2028 | 85.6% | 15.4s |
| memory | memory-01/recall | 3 | ✅ | final_answer | 2 | 1 | 2392 | 0 | 1172 | 3564 | 2156 | 43.7% | 8.8s |
| learning | learning-04 | 1 | ✅ | completed | 0 | 0 | 2846 | 0 | 0 | 2846 | 2846 | 未知 | 6.0s |
| learning | learning-04 | 2 | ✅ | completed | 0 | 0 | 2894 | 0 | 0 | 2894 | 2894 | 未知 | 6.2s |
| learning | learning-04 | 3 | ✅ | completed | 0 | 0 | 2848 | 0 | 0 | 2848 | 2848 | 未知 | 6.1s |

## 失败归因

### core · skill-15 · run#1
- [ran_ok] stop=context_error; expected=['final_answer']
- [skill] activated=['debug-python']; active skill 未在压缩后保留
- [answer] missing_keypoints=['int', 'ValueError']; answer='Agent stopped: context preparation failed: estimated input tokens (1194) exceed input budget (1188)'
- [compaction] compaction_events=[{'stage': 'none', 'trimmed': False, 'before': 955, 'after': 955, 'input_budget': 1188, 'trigger': 831, 'target': 534, 'summary_updated': False, 'summary_error': None}, {'stage': 'none', 'trimmed': False, 'before': 1194, 'after': 1194, 'input_budget': 1188, 'trigger': 831, 'target': 534, 'summary_updated': False, 'summary_error': None}]
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-67mxmopy/core/skill-15/run-1/trace.json`

### core · skill-15 · run#2
- [skill] activated=['debug-python']; active skill 未在压缩后保留
- [compaction] compaction_events=[{'stage': 'none', 'trimmed': False, 'before': 955, 'after': 955, 'input_budget': 1188, 'trigger': 831, 'target': 534, 'summary_updated': False, 'summary_error': None}, {'stage': 'none', 'trimmed': False, 'before': 1186, 'after': 1186, 'input_budget': 1188, 'trigger': 831, 'target': 534, 'summary_updated': False, 'summary_error': None}]
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-67mxmopy/core/skill-15/run-2/trace.json`

### core · skill-15 · run#3
- [ran_ok] stop=context_error; expected=['final_answer']
- [skill] activated=['debug-python']; active skill 未在压缩后保留
- [answer] missing_keypoints=['int', 'ValueError']; answer='Agent stopped: context preparation failed: estimated input tokens (1191) exceed input budget (1188)'
- [compaction] compaction_events=[{'stage': 'none', 'trimmed': False, 'before': 955, 'after': 955, 'input_budget': 1188, 'trigger': 831, 'target': 534, 'summary_updated': False, 'summary_error': None}, {'stage': 'none', 'trimmed': False, 'before': 1191, 'after': 1191, 'input_budget': 1188, 'trigger': 831, 'target': 534, 'summary_updated': False, 'summary_error': None}]
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-67mxmopy/core/skill-15/run-3/trace.json`
