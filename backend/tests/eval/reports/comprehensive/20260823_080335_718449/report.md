# Vesta Agent 综合评测报告

## 汇总

| 指标 | 值 |
| --- | --- |
| 样本数 | 12 |
| 通过数 | 4 |
| 样本通过率 | 33.3% |
| 稳定通过率 | 0.0% |
| 安全场景通过率 | 未知 |
| 平均 Steps | 1.6 |
| 平均模型调用 | 3.1 |
| 平均可计费 Token | 3931 |
| P95 可计费 Token | 7270 |
| 平均缓存命中率 | 74.6% |
| 平均耗时 | 15.7s |

## 运行信息

- Provider / Model：deepseek / deepseek-v4-flash
- Suites：core, memory, learning
- Tier：smoke
- Git Commit：35c7a84dee4d9a0460cc8583f4d975708e3d01df
- Scenario Digest：465dfde6ebf62dd22b5bf76e5e3a405d6c31bbcf32f19264897b7174b94a0db8
- 生成时间：2026-08-23T08:03:36.020956+00:00
- 运行现场：/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-y1v2t90n

## 分组结果

| Suite / Group | 通过 | 样本 | 通过率 |
| --- | --- | --- | --- |
| core / task | 2 | 3 | 66.7% |
| learning / learning | 2 | 6 | 33.3% |
| memory / memory | 0 | 3 | 0.0% |

## 分样本

| Suite | 场景 / Phase | Run | 结果 | Stop | Steps | Tools | Main | Summary | Reflection | Total | Chargeable | Cache | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core | eval-04 | 1 | ✅ | final_answer | 3 | 2 | 12954 | 0 | 0 | 12954 | 5146 | 70.7% | 20.6s |
| core | eval-04 | 2 | ❌ | final_answer | 3 | 5 | 14907 | 0 | 0 | 14907 | 4283 | 85.0% | 21.2s |
| core | eval-04 | 3 | ✅ | final_answer | 3 | 3 | 11785 | 0 | 0 | 11785 | 2697 | 88.2% | 16.2s |
| memory | memory-05/revise | 1 | ❌ | final_answer | 4 | 3 | 8153 | 0 | 1956 | 10109 | 5757 | 64.4% | 32.3s |
| memory | memory-05/revise | 2 | ❌ | final_answer | 3 | 3 | 8943 | 0 | 2462 | 11405 | 4621 | 83.8% | 28.8s |
| memory | memory-05/revise | 3 | ❌ | final_answer | 3 | 3 | 9083 | 0 | 2539 | 11622 | 7270 | 55.6% | 32.5s |
| learning | learning-02 | 1 | ✅ | completed | 0 | 0 | 2807 | 0 | 0 | 2807 | 2807 | 未知 | 6.2s |
| learning | learning-02 | 2 | ❌ | completed | 0 | 0 | 2583 | 0 | 0 | 2583 | 2583 | 未知 | 4.8s |
| learning | learning-02 | 3 | ✅ | completed | 0 | 0 | 2935 | 0 | 0 | 2935 | 2935 | 未知 | 7.5s |
| learning | learning-05b | 1 | ❌ | completed | 0 | 0 | 3120 | 0 | 0 | 3120 | 3120 | 未知 | 6.5s |
| learning | learning-05b | 2 | ❌ | completed | 0 | 0 | 2924 | 0 | 0 | 2924 | 2924 | 未知 | 5.5s |
| learning | learning-05b | 3 | ❌ | completed | 0 | 0 | 3027 | 0 | 0 | 3027 | 3027 | 未知 | 6.5s |

## 失败归因

### core · eval-04 · run#2
- [tools] called=['list_files', 'get_current_time', 'task_create', 'task_create', 'task_create']; count_failures=['task_create=3 期望 1']
- [task] new_tasks=3 期望 1; target=new 需要恰好一个新增 Task，实际 3
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-y1v2t90n/core/eval-04/run-2/trace.json`

### memory · memory-05/revise · run#1
- [reflection_action] actual=none expected=update
- [reflection_mutation] actual=False expected=True
- [stored_memory] content_missing=revision, revision=1 < 2
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-y1v2t90n/memory/memory-05/run-1/on/phase-revise/trace.json`

### memory · memory-05/revise · run#2
- [reflection_action] actual=None expected=update
- [reflection_mutation] actual=None expected=True
- [stored_memory] content_missing=revision, revision=1 < 2
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-y1v2t90n/memory/memory-05/run-2/on/phase-revise/trace.json`

### memory · memory-05/revise · run#3
- [reflection_action] actual=None expected=update
- [reflection_mutation] actual=None expected=True
- [stored_memory] content_missing=revision, revision=1 < 2
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-y1v2t90n/memory/memory-05/run-3/on/phase-revise/trace.json`

### learning · learning-02 · run#2
- [learning] candidate_count=0 expected 1; expected names ['python-runtime-debug'] not matched (actual: []); create_count=0 expected 1; action not create: []
- Pattern Mining：scanned=4, clusters=1
  - Cluster：Python runtime error debugging via traceback · tasks=['b1498352a6254e2c9e085e542f043555', 'c335420746124b138d5862a998d00d43', '4b6326d8c0174a739f7bfd73464aa388', 'af3c1ad840344283a6e435b4c50290d9']
- Distillation：cluster=Python runtime error debugging via traceback, action=none, reason=The evidence is too thin to support a stable procedure. All four tasks share only the final_steps summary ('reproduce error, read traceback, fix and run pytest') with no actual execution details, trace events, or concrete steps. Each task has only 1 run and no key facts or constraints. The summaries are generic and could describe any debugging workflow; there is no evidence of a validated, repeatable procedure beyond a trivial high-level loop. Without specific steps, pitfalls, or verification details, proposing a skill would be speculative., error=-

### learning · learning-05b · run#1
- [learning] candidate_count=0 expected 1; expected names ['debug-python'] not matched (actual: []); update_count=0 expected 1; action not update: []
- Pattern Mining：scanned=4, clusters=1
  - Cluster：Python Virtualenv Error Diagnosis and Repair · tasks=['18e79934266c495d82be6cd21ba9e840', '60d3c7b9700345e3827b4cdfca4cb4f5', '4dbbb40f44d64a72add44e8f29782563', '327808af062b4c6c8e0e15b8e0e8805a']
- Distillation：cluster=Python Virtualenv Error Diagnosis and Repair, action=none, reason=The four tasks share only the generic final steps '复现错误, 确认 virtualenv, 修复并验证' with no trace events, key facts, or concrete fix details. This is too thin to prove a stable, distinct procedure beyond what the existing 'debug-python' skill already covers (reproduce -> read traceback -> fix and verify). The virtualenv confirmation step is a minor variation of the same Python debugging family, but there is no evidence of stable new steps, pitfalls, or verification worth adding. Action 'none' is appropriate., error=-

### learning · learning-05b · run#2
- [learning] candidate_count=0 expected 1; expected names ['debug-python'] not matched (actual: []); update_count=0 expected 1; action not update: []
- Pattern Mining：scanned=4, clusters=1
  - Cluster：Python virtualenv troubleshooting · tasks=['5516510a4ca74ffba0054d6bf4a626a7', '54f7afdd01454434889f522a80fea68c', '47b309223655404a9c1f142e03047377', 'bcc89eb08c47467783a266370d337c6d']
- Distillation：cluster=Python virtualenv troubleshooting, action=none, reason=The cluster's procedure (reproduce error, confirm virtualenv, fix and verify) is already fully covered by the existing 'debug-python' skill body, which contains the same stable steps (reproduce, read traceback, fix and verify). The evidence is also thin—all tasks lack trace events and have only 2 runs each, with no concrete error details or fixes. This does not demonstrate a distinct, stable procedure beyond what the existing skill already captures., error=-

### learning · learning-05b · run#3
- [learning] candidate_count=0 expected 1; expected names ['debug-python'] not matched (actual: []); update_count=0 expected 1; action not update: []
- Pattern Mining：scanned=4, clusters=1
  - Cluster：Python 环境问题排查与修复 · tasks=['dace95321d4442a7808c3595b393ded6', 'e2a46927d092436db282dd0691b370ba', 'acda4f4ba1a3430b88ce12bebfa38ec8', '0fd2411be3d94936baa93215e79d3ccc']
- Distillation：cluster=Python 环境问题排查与修复, action=none, reason=The cluster evidence is extremely thin: all four tasks only report the same three high-level final steps (复现错误, 确认 virtualenv, 修复并验证) with no trace events, no concrete errors, no actual fixes, and only 2 runs each. This is insufficient to prove a stable, repeatable procedure beyond what the existing 'debug-python' skill already covers (reproduce, read traceback, fix and verify). The existing skill body already covers the same generic diagnostic flow, and there is no new stable step, pitfall, or verification detail to justify an update or create., error=-
