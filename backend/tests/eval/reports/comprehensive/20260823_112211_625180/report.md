# Vesta Agent 综合评测报告

## 汇总

| 指标 | 值 |
| --- | --- |
| 请求重复次数 | 3 |
| 预期样本数 | 3 |
| 实际样本数 | 3 |
| 样本完整性 | ✅ 完整 |
| 通过数 | 1 |
| 样本通过率 | 33.3% |
| 稳定通过率 | 0.0% |
| 安全场景通过率 | 未知 |
| 平均 Steps | 2.3 |
| 平均模型调用 | 3.3 |
| 平均可计费 Token | 2854 |
| P95 可计费 Token | 3893 |
| 平均缓存命中率 | 47.3% |
| 平均耗时 | 13.9s |

## 运行信息

- Provider / Model：deepseek / deepseek-v4-flash
- Suites：core
- Tier：regression
- Git Commit：35c7a84+working-tree-skill15-v3
- Scenario Digest：66e9d0f80b040f638392536a89c9aa536ab53ff8fc94b02b5bba2d67e4f34f82
- 生成时间：2026-08-23T11:22:11.930062+00:00
- 运行现场：/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-q7eq88xw

## 样本完整性

所有稳定性键均包含完整的重复运行样本。

| 稳定性样本 | 期望 Run | 实际 Run | 完整 |
| --- | --- | --- | --- |
| core/skill-15 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |

## 分组结果

| Suite / Group | 通过 | 样本 | 通过率 |
| --- | --- | --- | --- |
| core / skill | 1 | 3 | 33.3% |

## 分样本

| Suite | 场景 / Phase | Run | 结果 | Stop | Steps | Tools | Main | Summary | Reflection | Total | Chargeable | Cache | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core | skill-15 | 1 | ✅ | final_answer | 3 | 3 | 4798 | 887 | 0 | 5685 | 3893 | 39.1% | 17.7s |
| core | skill-15 | 2 | ❌ | final_answer | 2 | 2 | 2885 | 858 | 0 | 3743 | 2207 | 52.4% | 12.6s |
| core | skill-15 | 3 | ❌ | final_answer | 2 | 2 | 3021 | 977 | 0 | 3998 | 2462 | 50.2% | 11.2s |

## 失败归因

### core · skill-15 · run#2
- [skill] activated=['debug-python']; active skill 未在压缩后保留
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-q7eq88xw/core/skill-15/run-2/trace.json`

### core · skill-15 · run#3
- [skill] activated=['debug-python']; active skill 未在压缩后保留
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-q7eq88xw/core/skill-15/run-3/trace.json`
