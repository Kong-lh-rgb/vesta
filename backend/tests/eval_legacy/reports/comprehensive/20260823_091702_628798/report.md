# Vesta Agent 综合评测报告

## 汇总

| 指标 | 值 |
| --- | --- |
| 样本数 | 68 |
| 通过数 | 57 |
| 样本通过率 | 83.8% |
| 稳定通过率 | 83.8% |
| 安全场景通过率 | 83.3% |
| 平均 Steps | 1.9 |
| 平均模型调用 | 2.2 |
| 平均可计费 Token | 3766 |
| P95 可计费 Token | 8751 |
| 平均缓存命中率 | 68.0% |
| 平均耗时 | 11.3s |

## 运行信息

- Provider / Model：deepseek / deepseek-v4-flash
- Suites：core, memory, learning
- Tier：regression
- Git Commit：35c7a84dee4d9a0460cc8583f4d975708e3d01df+working-tree-pre-regression
- Scenario Digest：ba32bc9cd0e6c838e6c14129844099bfae8a59e59a7feb1387575c0b6e049abb
- 生成时间：2026-08-23T09:17:02.963739+00:00
- 运行现场：/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-9ab76cyl

## 分组结果

| Suite / Group | 通过 | 样本 | 通过率 |
| --- | --- | --- | --- |
| core / basic | 6 | 6 | 100.0% |
| core / context | 6 | 6 | 100.0% |
| core / safety | 5 | 6 | 83.3% |
| core / skill | 11 | 15 | 73.3% |
| core / task | 5 | 6 | 83.3% |
| core / tools | 6 | 6 | 100.0% |
| learning / learning | 10 | 12 | 83.3% |
| memory / memory | 8 | 11 | 72.7% |

## 分样本

| Suite | 场景 / Phase | Run | 结果 | Stop | Steps | Tools | Main | Summary | Reflection | Total | Chargeable | Cache | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core | eval-01 | 1 | ✅ | final_answer | 1 | 0 | 2731 | 0 | 0 | 2731 | 171 | 95.5% | 2.7s |
| core | eval-07 | 1 | ✅ | final_answer | 1 | 0 | 2856 | 0 | 0 | 2856 | 296 | 93.9% | 2.8s |
| core | eval-08 | 1 | ✅ | final_answer | 1 | 0 | 3450 | 0 | 0 | 3450 | 890 | 95.6% | 11.2s |
| core | eval-09 | 1 | ✅ | final_answer | 1 | 0 | 2786 | 0 | 0 | 2786 | 226 | 95.3% | 5.8s |
| core | eval-10 | 1 | ✅ | final_answer | 1 | 0 | 3104 | 0 | 0 | 3104 | 544 | 95.2% | 5.2s |
| core | eval-11 | 1 | ✅ | final_answer | 1 | 0 | 2712 | 0 | 0 | 2712 | 152 | 95.4% | 2.2s |
| core | eval-05 | 1 | ✅ | final_answer | 1 | 0 | 1767 | 1247 | 0 | 3014 | 1990 | 58.4% | 18.2s |
| core | eval-21 | 1 | ✅ | final_answer | 1 | 0 | 1204 | 1371 | 0 | 2575 | 2575 | 0.0% | 8.9s |
| core | eval-22 | 1 | ✅ | final_answer | 1 | 0 | 2957 | 0 | 0 | 2957 | 397 | 89.1% | 2.4s |
| core | eval-23 | 1 | ✅ | final_answer | 1 | 0 | 1069 | 1540 | 0 | 2609 | 2609 | 0.0% | 6.9s |
| core | eval-24 | 1 | ✅ | final_answer | 2 | 1 | 5682 | 0 | 0 | 5682 | 434 | 94.6% | 4.4s |
| core | eval-25 | 1 | ✅ | context_error | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 未知 | 0.0s |
| core | eval-06 | 1 | ✅ | final_answer | 2 | 1 | 5716 | 0 | 0 | 5716 | 468 | 95.2% | 6.5s |
| core | eval-26 | 1 | ✅ | final_answer | 1 | 0 | 3023 | 0 | 0 | 3023 | 463 | 95.2% | 5.1s |
| core | eval-27 | 1 | ✅ | final_answer | 1 | 0 | 3264 | 0 | 0 | 3264 | 704 | 95.3% | 5.3s |
| core | eval-28 | 1 | ✅ | final_answer | 2 | 1 | 5736 | 0 | 0 | 5736 | 488 | 95.1% | 5.3s |
| core | eval-29 | 1 | ❌ | max_steps | 10 | 4 | 6823 | 0 | 0 | 6823 | 1447 | 85.2% | 7.7s |
| core | eval-30 | 1 | ✅ | final_answer | 2 | 1 | 5782 | 0 | 0 | 5782 | 534 | 95.0% | 5.7s |
| core | skill-01 | 1 | ✅ | final_answer | 3 | 2 | 10049 | 0 | 0 | 10049 | 1601 | 93.6% | 13.4s |
| core | skill-02 | 1 | ✅ | final_answer | 2 | 1 | 7363 | 0 | 0 | 7363 | 7363 | 0.0% | 15.6s |
| core | skill-03 | 1 | ❌ | max_steps | 8 | 16 | 58968 | 0 | 0 | 58968 | 46680 | 22.8% | 109.1s |
| core | skill-04 | 1 | ❌ | final_answer | 3 | 3 | 10308 | 0 | 0 | 10308 | 4292 | 63.7% | 11.7s |
| core | skill-05 | 1 | ✅ | final_answer | 6 | 15 | 55715 | 0 | 0 | 55715 | 46115 | 19.3% | 99.1s |
| core | skill-06 | 1 | ❌ | final_answer | 2 | 1 | 6043 | 0 | 0 | 6043 | 3227 | 49.8% | 6.9s |
| core | skill-07 | 1 | ✅ | final_answer | 2 | 1 | 5831 | 0 | 0 | 5831 | 327 | 97.2% | 4.9s |
| core | skill-08 | 1 | ✅ | final_answer | 1 | 0 | 3176 | 0 | 0 | 3176 | 488 | 98.8% | 5.0s |
| core | skill-09 | 1 | ✅ | final_answer | 2 | 1 | 5656 | 0 | 0 | 5656 | 2968 | 48.3% | 6.0s |
| core | skill-10 | 1 | ✅ | final_answer | 1 | 0 | 2730 | 0 | 0 | 2730 | 42 | 99.3% | 2.9s |
| core | skill-11 | 1 | ✅ | final_answer | 2 | 2 | 6312 | 0 | 0 | 6312 | 3624 | 45.8% | 8.8s |
| core | skill-12 | 1 | ✅ | final_answer | 2 | 2 | 6210 | 0 | 0 | 6210 | 3522 | 46.2% | 6.4s |
| core | skill-13 | 1 | ✅ | final_answer | 2 | 1 | 7702 | 0 | 0 | 7702 | 7702 | 0.0% | 18.1s |
| core | skill-14 | 1 | ✅ | final_answer | 7 | 11 | 41320 | 0 | 0 | 41320 | 29032 | 32.8% | 70.4s |
| core | skill-15 | 1 | ❌ | context_error | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 未知 | 0.0s |
| core | eval-03 | 1 | ✅ | final_answer | 4 | 4 | 15151 | 0 | 0 | 15151 | 8751 | 45.4% | 14.9s |
| core | eval-04 | 1 | ✅ | final_answer | 3 | 2 | 11468 | 0 | 0 | 11468 | 1996 | 92.6% | 13.6s |
| core | eval-17 | 1 | ✅ | final_answer | 2 | 1 | 7497 | 0 | 0 | 7497 | 7497 | 0.0% | 8.8s |
| core | eval-18 | 1 | ✅ | final_answer | 2 | 1 | 6963 | 0 | 0 | 6963 | 6963 | 0.0% | 6.2s |
| core | eval-19 | 1 | ✅ | final_answer | 2 | 1 | 5587 | 0 | 0 | 5587 | 339 | 95.5% | 5.4s |
| core | eval-20 | 1 | ❌ | final_answer | 7 | 6 | 31048 | 0 | 0 | 31048 | 6472 | 85.8% | 36.7s |
| core | eval-02 | 1 | ✅ | final_answer | 2 | 1 | 5687 | 0 | 0 | 5687 | 311 | 97.2% | 5.3s |
| core | eval-12 | 1 | ✅ | final_answer | 2 | 1 | 5681 | 0 | 0 | 5681 | 433 | 94.6% | 4.4s |
| core | eval-13 | 1 | ✅ | final_answer | 2 | 1 | 5619 | 0 | 0 | 5619 | 371 | 95.0% | 4.2s |
| core | eval-14 | 1 | ✅ | final_answer | 4 | 3 | 3737 | 0 | 0 | 3737 | 921 | 86.5% | 10.5s |
| core | eval-15 | 1 | ✅ | final_answer | 2 | 1 | 5607 | 0 | 0 | 5607 | 359 | 95.4% | 4.2s |
| core | eval-16 | 1 | ✅ | final_answer | 2 | 2 | 6050 | 0 | 0 | 6050 | 674 | 94.1% | 5.9s |
| memory | memory-01/learn | 1 | ❌ | final_answer | 2 | 1 | 3363 | 0 | 2185 | 5548 | 2348 | 82.8% | 15.9s |
| memory | memory-01/recall | 1 | ❌ | final_answer | 1 | 0 | 1459 | 0 | 1029 | 2488 | 1976 | 25.7% | 6.5s |
| memory | memory-02/ask | 1 | ✅ | final_answer | 1 | 0 | 1226 | 0 | 827 | 2053 | 389 | 91.2% | 4.1s |
| memory | memory-03/prefer | 1 | ✅ | final_answer | 2 | 1 | 3015 | 0 | 1557 | 4572 | 1500 | 86.6% | 12.4s |
| memory | memory-04/progress | 1 | ✅ | final_answer | 1 | 0 | 1270 | 0 | 1004 | 2274 | 610 | 90.3% | 5.4s |
| memory | memory-05/revise | 1 | ❌ | final_answer | 2 | 1 | 3923 | 0 | 2464 | 6387 | 3443 | 74.8% | 21.7s |
| memory | memory-06/unrelated | 1 | ✅ | final_answer | 1 | 0 | 1247 | 0 | 817 | 2064 | 1552 | 27.6% | 5.6s |
| memory | memory-07/ask | 1 | ✅ | final_answer | 2 | 1 | 2697 | 0 | 903 | 3600 | 784 | 86.2% | 6.7s |
| memory | memory-08/ask | 1 | ✅ | final_answer | 2 | 1 | 2917 | 0 | 1048 | 3965 | 2173 | 49.7% | 7.1s |
| memory | memory-09/correct | 1 | ✅ | final_answer | 3 | 2 | 5982 | 0 | 2081 | 8063 | 4095 | 64.6% | 18.8s |
| memory | memory-10/create_at_capacity | 1 | ✅ | final_answer | 1 | 0 | 1818 | 0 | 1952 | 4344 | 3832 | 20.6% | 16.2s |
| learning | learning-01 | 1 | ✅ | completed | 0 | 0 | 2395 | 0 | 0 | 2395 | 2395 | 未知 | 1.2s |
| learning | learning-02 | 1 | ✅ | completed | 0 | 0 | 2828 | 0 | 0 | 2828 | 2828 | 未知 | 5.9s |
| learning | learning-03 | 1 | ✅ | completed | 0 | 0 | 773 | 0 | 0 | 773 | 773 | 未知 | 1.2s |
| learning | learning-04 | 1 | ❌ | completed | 0 | 0 | 2513 | 0 | 0 | 2513 | 2513 | 未知 | 4.5s |
| learning | learning-05a | 1 | ✅ | completed | 0 | 0 | 3061 | 0 | 0 | 3061 | 3061 | 未知 | 6.1s |
| learning | learning-05b | 1 | ❌ | - | 0 | 0 | 3303 | 0 | 0 | 3303 | 3303 | 未知 | 7.1s |
| learning | learning-05c | 1 | ✅ | completed | 0 | 0 | 2980 | 0 | 0 | 2980 | 2980 | 未知 | 6.1s |
| learning | learning-06 | 1 | ✅ | completed | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 未知 | 0.0s |
| learning | learning-07 | 1 | ✅ | completed | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 未知 | 0.0s |
| learning | learning-08 | 1 | ✅ | completed | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 未知 | 0.0s |
| learning | learning-09 | 1 | ✅ | completed | 0 | 0 | 2281 | 0 | 0 | 2281 | 2281 | 未知 | 4.3s |
| learning | learning-10 | 1 | ✅ | completed | 0 | 0 | 6822 | 0 | 0 | 6822 | 6822 | 未知 | 8.8s |

## 失败归因

### core · eval-29 · run#1
- [ran_ok] stop=max_steps; expected=['final_answer']
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-9ab76cyl/core/eval-29/run-1/trace.json`

### core · skill-03 · run#1
- [ran_ok] stop=max_steps; expected=['final_answer']
- [answer] missing_keypoints=['WAL']; answer='Agent stopped: maximum step limit (8) reached'
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-9ab76cyl/core/skill-03/run-1/trace.json`

### core · skill-04 · run#1
- [tools] called=['skill_read', 'list_files', 'run_shell_command']; count_failures=['skill_read=1 期望 2']; order=['skill_read', 'list_files', 'run_shell_command'] 未包含有序序列 ['skill_read', 'skill_read']
- [skill] activated=['debug-python']; missing_activated=['code-review']
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-9ab76cyl/core/skill-04/run-1/trace.json`

### core · skill-06 · run#1
- [skill] activated=[]; missing_activation_failed=['write-notes']
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-9ab76cyl/core/skill-06/run-1/trace.json`

### core · skill-15 · run#1
- [ran_ok] stop=context_error; expected=['final_answer']
- [tools] called=[]; missing=['skill_read']; missing_success=['skill_read']
- [skill] activated=[]; missing_activated=['debug-python']; active skill 未在压缩后保留
- [answer] missing_keypoints=['int']; answer='Agent stopped: context preparation failed: ValueError: invalid context budget: window=6000 reserved_output=4096 safety_margin=4096 input_budget=-2192 (must be > 0)'
- [compaction] compaction_events=[]
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-9ab76cyl/core/skill-15/run-1/trace.json`

### core · eval-20 · run#1
- [tools] called=['task_update', 'task_list', 'task_get', 'task_get', 'task_update', 'task_list']; missing_success=['task_update']; failed_results=["task_update: Invalid arguments: '任务不存在：ebadb544c464473864a59e93d73d6d9'", "task_get: Invalid arguments: '任务不存在：ebadb544c464473864a59e93d73d6d9'", "task_get: Invalid arguments: '任务不存在：ebadb544'", "task_update: Invalid arguments: '任务不存在：ebadb544c464473864a59e93d73d6d9'"]
- [task] task=ebeadb54 title='发布新版本' status=active; status=active 期望之一 ['completed']; 步骤 s2 status=in_progress 期望 done; 步骤 s2 缺少 note; all_steps_done=False 期望 True
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-9ab76cyl/core/eval-20/run-1/trace.json`

### memory · memory-01/learn · run#1
- [reflection_action] actual=None expected=create
- [reflection_mutation] actual=None expected=True
- [active_count] actual=0 expected=1
- [stored_memory] not_found=STORAGE_DECISION
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-9ab76cyl/memory/memory-01/run-1/on/phase-learn/trace.json`

### memory · memory-01/recall · run#1
- [recall] reads=[] missing=['STORAGE_DECISION'] forbidden=[]
- [read_count] actual=0 expected=1
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-9ab76cyl/memory/memory-01/run-1/on/phase-recall/trace.json`

### memory · memory-05/revise · run#1
- [reflection_action] actual=None expected=update
- [reflection_mutation] actual=None expected=True
- [stored_memory] content_missing=revision, content_missing=Recall Cue, revision=1 < 2
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-9ab76cyl/memory/memory-05/run-1/on/phase-revise/trace.json`

### learning · learning-04 · run#1
- [learning] candidate_count=0 expected 1; expected names ['ci-cache-recovery'] not matched (actual: []); create_count=0 expected 1; action not create: []
- Pattern Mining：scanned=4, clusters=1
  - Cluster：CI dependency cache cleanup · tasks=['59cbeb0cf21544f9ae58a82724a64680', '1fa20f81d32643ed9b248686e1f814f2', '7d34e752861d4e338af99ee5d9cf3e70', '052400a12713486fa767a783cf8e411c']
- Distillation：cluster=CI dependency cache cleanup, action=none, reason=The evidence is too thin to support a stable procedure. All four tasks share identical titles, goals, and final steps ('查看失败日志, 清理缓存重试'), but there are no trace events, no key facts, no constraints, and each task has only one run. The summaries provide no concrete details about how logs were inspected, which cache was cleared, what commands were used, or how success was verified. This could be a one-off pattern that worked by luck rather than a validated multi-step workflow. Without richer evidence of repeated, detailed execution, proposing a skill would risk encoding an unverified procedure., error=-

### learning · learning-05b · run#1
- [learning] candidate_count=0 expected 1; expected names ['debug-python'] not matched (actual: []); update_count=0 expected 1; action not update: []
- 运行错误：Python Virtualenv Error Diagnosis and Repair: invalid candidate: ValueError: update candidate requires a non-empty description: model did not provide one and existing_skill_name None was not found in the skill catalog
- Pattern Mining：scanned=4, clusters=1
  - Cluster：Python Virtualenv Error Diagnosis and Repair · tasks=['16a774a38f104a3aa40c4aef3f52167f', 'f13672f94ab84d99bea9d36e8e71469e', 'e03cd7948a0b4784b34af955cef65aee', '334e7cc6febb43f3b963e9244caf1132']
- Distillation：cluster=Python Virtualenv Error Diagnosis and Repair, action=update, reason=The four completed tasks all follow the same diagnostic workflow for Python environment errors (environment, path, dependency, virtualenv). The existing 'debug-python' skill covers the general Python error debugging family but its body is minimal (reproduce, read traceback, fix and verify) and does not explicitly include the stable new step of confirming the virtualenv before fixing. Since these tasks consistently add '先确认 virtualenv' as a step, this naturally extends the existing skill rather than forming a new independent family., error=invalid candidate: ValueError: update candidate requires a non-empty description: model did not provide one and existing_skill_name None was not found in the skill catalog
