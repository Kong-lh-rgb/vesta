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
| 平均 Steps | 0.0 |
| 平均模型调用 | 3.0 |
| 平均可计费 Token | 3290 |
| P95 可计费 Token | 3368 |
| 平均缓存命中率 | 未知 |
| 平均耗时 | 8.1s |

## 运行信息

- Provider / Model：deepseek / deepseek-v4-flash
- Suites：learning
- Tier：regression
- Git Commit：-
- Scenario Digest：06f262f02073fe059a9d6a21b54cffd1b53fbf0577adb39c74eac6d106dff729
- 生成时间：2026-08-23T13:16:18.164410+00:00
- 运行现场：/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-350iu7na

## 样本完整性

所有稳定性键均包含完整的重复运行样本。

| 稳定性样本 | 期望 Run | 实际 Run | 完整 |
| --- | --- | --- | --- |
| learning/learning-05a (on) | [1, 2, 3] | [1, 2, 3] | ✅ |

## 分组结果

| Suite / Group | 通过 | 样本 | 通过率 |
| --- | --- | --- | --- |
| learning / learning | 3 | 3 | 100.0% |

## 分样本

| Suite | 场景 / Phase | Run | 结果 | Stop | Steps | Tools | Main | Summary | Reflection | Total | Chargeable | Cache | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| learning | learning-05a | 1 | ✅ | completed | 0 | 0 | 3229 | 0 | 0 | 3229 | 3229 | 未知 | 9.1s |
| learning | learning-05a | 2 | ✅ | completed | 0 | 0 | 3368 | 0 | 0 | 3368 | 3368 | 未知 | 7.5s |
| learning | learning-05a | 3 | ✅ | completed | 0 | 0 | 3273 | 0 | 0 | 3273 | 3273 | 未知 | 7.8s |

## 失败归因

无失败样本。