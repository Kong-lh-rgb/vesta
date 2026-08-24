# Vesta Agent 综合评测报告

## 汇总

| 指标 | 值 |
| --- | --- |
| 样本数 | 12 |
| 通过数 | 10 |
| 样本通过率 | 83.3% |
| 稳定通过率 | 50.0% |
| 安全场景通过率 | 未知 |
| 平均 Steps | 1.0 |
| 平均模型调用 | 2.5 |
| 平均可计费 Token | 2721 |
| P95 可计费 Token | 3718 |
| 平均缓存命中率 | 78.5% |
| 平均耗时 | 10.6s |

## 运行信息

- Provider / Model：deepseek / deepseek-v4-flash
- Suites：core, memory, learning
- Tier：smoke
- Git Commit：35c7a84dee4d9a0460cc8583f4d975708e3d01df
- Scenario Digest：1147e45d342aa6888d07677a39175fcad2ac3fce8af2527d2d492b652f056aee
- 生成时间：2026-08-23T08:15:27.269188+00:00
- 运行现场：/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-ndmwpq75

## 分组结果

| Suite / Group | 通过 | 样本 | 通过率 |
| --- | --- | --- | --- |
| core / task | 3 | 3 | 100.0% |
| learning / learning | 5 | 6 | 83.3% |
| memory / memory | 2 | 3 | 66.7% |

## 分样本

| Suite | 场景 / Phase | Run | 结果 | Stop | Steps | Tools | Main | Summary | Reflection | Total | Chargeable | Cache | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core | eval-04 | 1 | ✅ | final_answer | 2 | 1 | 7062 | 0 | 0 | 7062 | 1302 | 90.2% | 8.3s |
| core | eval-04 | 2 | ✅ | final_answer | 2 | 1 | 7265 | 0 | 0 | 7265 | 1505 | 89.2% | 8.8s |
| core | eval-04 | 3 | ✅ | final_answer | 2 | 1 | 7799 | 0 | 0 | 7799 | 1655 | 91.0% | 10.6s |
| memory | memory-05/revise | 1 | ✅ | final_answer | 2 | 1 | 3410 | 0 | 2100 | 5510 | 3718 | 47.4% | 17.0s |
| memory | memory-05/revise | 2 | ✅ | final_answer | 2 | 1 | 3374 | 0 | 2094 | 5468 | 2524 | 76.4% | 16.6s |
| memory | memory-05/revise | 3 | ❌ | final_answer | 2 | 1 | 4082 | 0 | 2369 | 6451 | 3507 | 76.6% | 23.5s |
| learning | learning-02 | 1 | ✅ | completed | 0 | 0 | 2911 | 0 | 0 | 2911 | 2911 | 未知 | 7.0s |
| learning | learning-02 | 2 | ✅ | completed | 0 | 0 | 2895 | 0 | 0 | 2895 | 2895 | 未知 | 7.0s |
| learning | learning-02 | 3 | ✅ | completed | 0 | 0 | 2818 | 0 | 0 | 2818 | 2818 | 未知 | 6.7s |
| learning | learning-05b | 1 | ✅ | completed | 0 | 0 | 3259 | 0 | 0 | 3259 | 3259 | 未知 | 7.7s |
| learning | learning-05b | 2 | ❌ | completed | 0 | 0 | 3218 | 0 | 0 | 3218 | 3218 | 未知 | 6.4s |
| learning | learning-05b | 3 | ✅ | completed | 0 | 0 | 3337 | 0 | 0 | 3337 | 3337 | 未知 | 8.1s |

## 失败归因

### memory · memory-05/revise · run#3
- [reflection_action] actual=None expected=update
- [reflection_mutation] actual=None expected=True
- [stored_memory] content_missing=revision, content_missing=Recall Cue, revision=1 < 2
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-ndmwpq75/memory/memory-05/run-3/on/phase-revise/trace.json`

### learning · learning-05b · run#2
- [learning] candidate_count=0 expected 1; expected names ['debug-python'] not matched (actual: []); update_count=0 expected 1; action not update: []
- Pattern Mining：scanned=4, clusters=1
  - Cluster：Python virtualenv error diagnosis and repair · tasks=['a81364e4d6ec4490b117853c980a4b7c', '90b4432faee84201a88fc356e4c822f6', 'd705a30f7b12448e8e9bb9a9b433acff', '24effc6d90d149378eacb3975018c9d3']
- Distillation：cluster=Python virtualenv error diagnosis and repair, action=none, reason=The existing skill 'debug-python' already covers the same task family (Python error diagnosis and repair) with the same core steps: reproduce, read traceback, fix and verify. The cluster's procedure (reproduce error, confirm virtualenv, fix, verify) is a natural extension of this existing skill's body, but the evidence is too thin to justify an update: all four tasks share identical tool sequences and only add a single step ('confirm virtualenv') without demonstrating distinct stable pitfalls or verification methods beyond what the existing skill already implies. The tasks appear to be near-duplicates of the same workflow rather than providing new, validated knowledge that would meaningfully extend the existing skill. Therefore, no action is warranted., error=-
