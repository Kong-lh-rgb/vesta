# Vesta Agent 综合评测报告

## 汇总

| 指标 | 值 |
| --- | --- |
| 样本数 | 12 |
| 通过数 | 5 |
| 样本通过率 | 41.7% |
| 稳定通过率 | 25.0% |
| 安全场景通过率 | 未知 |
| 平均 Steps | 1.1 |
| 平均模型调用 | 2.6 |
| 平均可计费 Token | 2553 |
| P95 可计费 Token | 3006 |
| 平均缓存命中率 | 79.8% |
| 平均耗时 | 9.7s |

## 运行信息

- Provider / Model：deepseek / deepseek-v4-flash
- Suites：core, memory, learning
- Tier：smoke
- Git Commit：35c7a84dee4d9a0460cc8583f4d975708e3d01df
- Scenario Digest：c3a972e83b13215ef9f7b0bcbdce278cc423cc643cac45d4f7900b04b0909529
- 生成时间：2026-08-23T08:10:30.578940+00:00
- 运行现场：/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-a7i25f1g

## 分组结果

| Suite / Group | 通过 | 样本 | 通过率 |
| --- | --- | --- | --- |
| core / task | 3 | 3 | 100.0% |
| learning / learning | 2 | 6 | 33.3% |
| memory / memory | 0 | 3 | 0.0% |

## 分样本

| Suite | 场景 / Phase | Run | 结果 | Stop | Steps | Tools | Main | Summary | Reflection | Total | Chargeable | Cache | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core | eval-04 | 1 | ✅ | final_answer | 2 | 1 | 7304 | 0 | 0 | 7304 | 2952 | 66.7% | 9.0s |
| core | eval-04 | 2 | ✅ | final_answer | 2 | 1 | 7255 | 0 | 0 | 7255 | 1367 | 91.0% | 8.8s |
| core | eval-04 | 3 | ✅ | final_answer | 2 | 1 | 7519 | 0 | 0 | 7519 | 1631 | 88.8% | 10.7s |
| memory | memory-05/revise | 1 | ❌ | final_answer | 2 | 1 | 3582 | 0 | 1553 | 5135 | 2191 | 76.2% | 14.9s |
| memory | memory-05/revise | 2 | ❌ | final_answer | 3 | 2 | 5918 | 0 | 1529 | 7447 | 2839 | 80.4% | 19.3s |
| memory | memory-05/revise | 3 | ❌ | final_answer | 2 | 1 | 3541 | 0 | 1662 | 5203 | 2387 | 75.7% | 15.9s |
| learning | learning-02 | 1 | ✅ | completed | 0 | 0 | 2829 | 0 | 0 | 2829 | 2829 | 未知 | 6.5s |
| learning | learning-02 | 2 | ❌ | completed | 0 | 0 | 2517 | 0 | 0 | 2517 | 2517 | 未知 | 4.6s |
| learning | learning-02 | 3 | ✅ | completed | 0 | 0 | 2971 | 0 | 0 | 2971 | 2971 | 未知 | 7.8s |
| learning | learning-05b | 1 | ❌ | completed | 0 | 0 | 2995 | 0 | 0 | 2995 | 2995 | 未知 | 6.0s |
| learning | learning-05b | 2 | ❌ | completed | 0 | 0 | 3006 | 0 | 0 | 3006 | 3006 | 未知 | 6.7s |
| learning | learning-05b | 3 | ❌ | completed | 0 | 0 | 2948 | 0 | 0 | 2948 | 2948 | 未知 | 6.1s |

## 失败归因

### memory · memory-05/revise · run#1
- [reflection_action] actual=none expected=update
- [reflection_mutation] actual=False expected=True
- [stored_memory] content_missing=revision, content_missing=Recall Cue, revision=1 < 2
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-a7i25f1g/memory/memory-05/run-1/on/phase-revise/trace.json`

### memory · memory-05/revise · run#2
- [reflection_action] actual=none expected=update
- [reflection_mutation] actual=False expected=True
- [stored_memory] content_missing=revision, content_missing=Recall Cue, revision=1 < 2
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-a7i25f1g/memory/memory-05/run-2/on/phase-revise/trace.json`

### memory · memory-05/revise · run#3
- [reflection_action] actual=none expected=update
- [reflection_mutation] actual=False expected=True
- [stored_memory] content_missing=revision, content_missing=Recall Cue, revision=1 < 2
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-a7i25f1g/memory/memory-05/run-3/on/phase-revise/trace.json`

### learning · learning-02 · run#2
- [learning] candidate_count=0 expected 1; expected names ['python-runtime-debug'] not matched (actual: []); create_count=0 expected 1; action not create: []
- Pattern Mining：scanned=4, clusters=1
  - Cluster：Python 异常修复流程 · tasks=['fe908beefa81421fbc884238d01b2686', 'c038ddff13ce459e9dad0942f7b97897', '686d8fc8574c4fc99969954aa01ea7be', 'fd533e31033b4ecdba3d760fa9b6fb53']
- Distillation：cluster=Python 异常修复流程, action=none, reason=The evidence is too thin to support a stable, worth-keeping procedure. Each task has only 1 run, no trace events, no key facts, and the 'final steps' are a generic three-step summary (reproduce, read traceback, fix and run pytest) that lacks any concrete details about how the specific exception types (AttributeError, KeyError, TypeError, ImportError) were diagnosed or fixed. There is no evidence of repeated validation across runs, no specific pitfalls, and no verification details beyond running pytest. This appears to be a high-level pattern that could apply to any Python debugging, but without concrete procedural steps or demonstrated stability, proposing a skill would be speculative., error=-

### learning · learning-05b · run#1
- [learning] candidate_count=0 expected 1; expected names ['debug-python'] not matched (actual: []); update_count=0 expected 1; action not update: []
- Pattern Mining：scanned=4, clusters=1
  - Cluster：Python virtualenv troubleshooting · tasks=['2a8678ef83c345ca9c16e234eb199932', '3ed0c07d026945aca70c814634ea432f', 'e0587da673c6406abcb0373c971625e3', '2b5e158aba094becb45cd801e22b7e21']
- Distillation：cluster=Python virtualenv troubleshooting, action=none, reason=The cluster's procedure (reproduce error, confirm virtualenv, fix and verify) is already fully covered by the existing 'debug-python' skill, which contains the same core steps (reproduce, read traceback, fix and verify). The virtualenv-specific detail is a natural instance of that general debugging flow, not an independent task family. Evidence is also thin (no trace events, only final steps), so no new stable procedure beyond the existing skill is demonstrated., error=-

### learning · learning-05b · run#2
- [learning] candidate_count=0 expected 1; expected names ['debug-python'] not matched (actual: []); update_count=0 expected 1; action not update: []
- Pattern Mining：scanned=4, clusters=1
  - Cluster：Python Virtualenv Error Diagnosis and Repair · tasks=['7c1e2ce19a744a3bb7a5c5b592e36026', '2ee33ad2bda045a0ba87116072a84752', '9fa65dfe93f347129bb8a0c055712634', '307e10a840bf4103a1fcfaa9c101d2cc']
- Distillation：cluster=Python Virtualenv Error Diagnosis and Repair, action=none, reason=The four tasks share only generic final steps (reproduce error, confirm virtualenv, fix and verify) with no trace events, no concrete error details, no specific fixes, and no validation evidence. This is too thin to prove a stable, reusable procedure beyond what the existing 'debug-python' skill already covers (reproduce, read traceback, fix and verify). The pattern is essentially the same generic debugging family already captured by the existing skill, and there is no new stable step, pitfall, or verification detail to justify an update or create., error=-

### learning · learning-05b · run#3
- [learning] candidate_count=0 expected 1; expected names ['debug-python'] not matched (actual: []); update_count=0 expected 1; action not update: []
- Pattern Mining：scanned=4, clusters=1
  - Cluster：Python Virtualenv Error Diagnosis and Repair · tasks=['1e8bd01e634d401ba0a4bbb249d149ae', 'ae0a09c3473549bc887119954f67f19a', '30a97a4d149f4379897a19a9a3f411e2', 'f78978c16e5041f3912bbfe9cd977950']
- Distillation：cluster=Python Virtualenv Error Diagnosis and Repair, action=none, reason=The cluster's procedure (reproduce error, confirm virtualenv, fix and verify) is already fully covered by the existing 'debug-python' skill body, which contains the same stable steps (reproduce, read traceback, fix and verify). The evidence is also thin—each task has only 2 runs and no trace events, so no new stable steps or pitfalls beyond the existing skill are demonstrated. No pending candidates exist, but the pattern is a subset of the existing skill's family and adds no novel reusable content., error=-
