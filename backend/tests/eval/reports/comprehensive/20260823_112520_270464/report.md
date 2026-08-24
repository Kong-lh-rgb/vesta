# Vesta Agent 综合评测报告

## 汇总

| 指标 | 值 |
| --- | --- |
| 请求重复次数 | 3 |
| 预期样本数 | 3 |
| 实际样本数 | 3 |
| 样本完整性 | ✅ 完整 |
| 通过数 | 2 |
| 样本通过率 | 66.7% |
| 稳定通过率 | 0.0% |
| 安全场景通过率 | 未知 |
| 平均 Steps | 3.0 |
| 平均模型调用 | 3.7 |
| 平均可计费 Token | 2688 |
| P95 可计费 Token | 3012 |
| 平均缓存命中率 | 61.3% |
| 平均耗时 | 14.4s |

## 运行信息

- Provider / Model：deepseek / deepseek-v4-flash
- Suites：core
- Tier：regression
- Git Commit：35c7a84+working-tree-skill15-v4
- Scenario Digest：66e9d0f80b040f638392536a89c9aa536ab53ff8fc94b02b5bba2d67e4f34f82
- 生成时间：2026-08-23T11:25:20.563186+00:00
- 运行现场：/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-0rap7psw

## 样本完整性

所有稳定性键均包含完整的重复运行样本。

| 稳定性样本 | 期望 Run | 实际 Run | 完整 |
| --- | --- | --- | --- |
| core/skill-15 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |

## 分组结果

| Suite / Group | 通过 | 样本 | 通过率 |
| --- | --- | --- | --- |
| core / skill | 2 | 3 | 66.7% |

## 分样本

| Suite | 场景 / Phase | Run | 结果 | Stop | Steps | Tools | Main | Summary | Reflection | Total | Chargeable | Cache | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core | skill-15 | 1 | ✅ | final_answer | 3 | 3 | 5290 | 922 | 0 | 6212 | 3012 | 65.4% | 18.5s |
| core | skill-15 | 2 | ❌ | context_error | 3 | 3 | 2812 | 937 | 0 | 3749 | 2213 | 51.6% | 10.1s |
| core | skill-15 | 3 | ✅ | final_answer | 3 | 3 | 5114 | 925 | 0 | 6039 | 2839 | 66.8% | 14.7s |

## 失败归因

### core · skill-15 · run#2
- [ran_ok] stop=context_error; expected=['final_answer']
- [answer] missing_keypoints=['int', 'ValueError']; answer='Agent stopped: context preparation failed: estimated input tokens (1697) exceed input budget (1688)'
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-0rap7psw/core/skill-15/run-2/trace.json`
