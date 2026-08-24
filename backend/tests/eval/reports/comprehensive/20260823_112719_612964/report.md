# Vesta Agent 综合评测报告

## 汇总

| 指标 | 值 |
| --- | --- |
| 请求重复次数 | 3 |
| 预期样本数 | 3 |
| 实际样本数 | 3 |
| 样本完整性 | ✅ 完整 |
| 通过数 | 3 |
| 样本通过率 | 100.0% |
| 稳定通过率 | 100.0% |
| 安全场景通过率 | 未知 |
| 平均 Steps | 2.7 |
| 平均模型调用 | 4.0 |
| 平均可计费 Token | 2956 |
| P95 可计费 Token | 3656 |
| 平均缓存命中率 | 56.9% |
| 平均耗时 | 14.0s |

## 运行信息

- Provider / Model：deepseek / deepseek-v4-flash
- Suites：core
- Tier：regression
- Git Commit：35c7a84+working-tree-skill15-v5
- Scenario Digest：3ea942863ef5df17014a9df546e4ccdf7ee3eeaf7d589400d652e68f913dad46
- 生成时间：2026-08-23T11:27:19.928591+00:00
- 运行现场：/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-65fwos8e

## 样本完整性

所有稳定性键均包含完整的重复运行样本。

| 稳定性样本 | 期望 Run | 实际 Run | 完整 |
| --- | --- | --- | --- |
| core/skill-15 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |

## 分组结果

| Suite / Group | 通过 | 样本 | 通过率 |
| --- | --- | --- | --- |
| core / skill | 3 | 3 | 100.0% |

## 分样本

| Suite | 场景 / Phase | Run | 结果 | Stop | Steps | Tools | Main | Summary | Reflection | Total | Chargeable | Cache | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core | skill-15 | 1 | ✅ | final_answer | 3 | 3 | 4877 | 868 | 0 | 5745 | 2673 | 66.6% | 15.0s |
| core | skill-15 | 2 | ✅ | final_answer | 3 | 3 | 4762 | 1838 | 0 | 6600 | 3656 | 54.5% | 15.8s |
| core | skill-15 | 3 | ✅ | final_answer | 2 | 2 | 3167 | 907 | 0 | 4074 | 2538 | 49.6% | 11.2s |

## 失败归因

无失败样本。