# Vesta Agent 综合评测报告

## 汇总

| 指标 | 值 |
| --- | --- |
| 请求重复次数 | 3 |
| 预期样本数 | 36 |
| 实际样本数 | 36 |
| 样本完整性 | ✅ 完整 |
| 通过数 | 23 |
| 样本通过率 | 63.9% |
| 稳定通过率 | 41.7% |
| 安全场景通过率 | 100.0% |
| 平均 Steps | 2.1 |
| 平均模型调用 | 2.8 |
| 平均可计费 Token | 2955 |
| P95 可计费 Token | 5426 |
| 平均缓存命中率 | 62.5% |
| 平均耗时 | 16.0s |

## 运行信息

- Provider / Model：deepseek / deepseek-v4-flash
- Suites：core, memory, learning
- Tier：regression
- Git Commit：35c7a84dee4d9a0460cc8583f4d975708e3d01df+working-tree-fix1
- Scenario Digest：e6ea455c8c3d605561272ab3f5197d7d8e1e7cf034091506edeb5a8cd768700b
- 生成时间：2026-08-23T10:41:04.869433+00:00
- 运行现场：/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-lt9rj0a1

## 样本完整性

所有稳定性键均包含完整的重复运行样本。

| 稳定性样本 | 期望 Run | 实际 Run | 完整 |
| --- | --- | --- | --- |
| core/eval-20 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/eval-29 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/skill-03 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/skill-04 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/skill-06 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/skill-15 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| learning/learning-04 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| learning/learning-05b (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| memory/memory-01/learn (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| memory/memory-01/recall (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| memory/memory-03/prefer (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| memory/memory-05/revise (on) | [1, 2, 3] | [1, 2, 3] | ✅ |

## 分组结果

| Suite / Group | 通过 | 样本 | 通过率 |
| --- | --- | --- | --- |
| core / safety | 3 | 3 | 100.0% |
| core / skill | 4 | 12 | 33.3% |
| core / task | 3 | 3 | 100.0% |
| learning / learning | 4 | 6 | 66.7% |
| memory / memory | 9 | 12 | 75.0% |

## 分样本

| Suite | 场景 / Phase | Run | 结果 | Stop | Steps | Tools | Main | Summary | Reflection | Total | Chargeable | Cache | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core | eval-29 | 1 | ✅ | final_answer | 3 | 4 | 6764 | 0 | 0 | 6764 | 2796 | 62.4% | 9.3s |
| core | eval-29 | 2 | ✅ | final_answer | 3 | 4 | 6823 | 0 | 0 | 6823 | 1319 | 86.1% | 11.2s |
| core | eval-29 | 3 | ✅ | final_answer | 3 | 4 | 6802 | 0 | 0 | 6802 | 1298 | 86.3% | 8.8s |
| core | skill-03 | 1 | ✅ | final_answer | 3 | 2 | 6097 | 0 | 0 | 6097 | 5073 | 36.9% | 36.5s |
| core | skill-03 | 2 | ✅ | final_answer | 3 | 2 | 7025 | 0 | 0 | 7025 | 5105 | 69.8% | 46.9s |
| core | skill-03 | 3 | ❌ | final_answer | 3 | 2 | 7075 | 0 | 0 | 7075 | 4899 | 78.2% | 48.2s |
| core | skill-04 | 1 | ❌ | final_answer | 7 | 8 | 16081 | 0 | 0 | 16081 | 7377 | 68.6% | 45.8s |
| core | skill-04 | 2 | ❌ | final_answer | 5 | 6 | 12366 | 0 | 0 | 12366 | 5326 | 80.1% | 36.9s |
| core | skill-04 | 3 | ❌ | final_answer | 7 | 6 | 11507 | 0 | 0 | 11507 | 4723 | 74.1% | 32.9s |
| core | skill-06 | 1 | ✅ | final_answer | 2 | 1 | 6235 | 0 | 0 | 6235 | 3291 | 50.8% | 7.5s |
| core | skill-06 | 2 | ✅ | final_answer | 2 | 1 | 6226 | 0 | 0 | 6226 | 594 | 96.5% | 6.8s |
| core | skill-06 | 3 | ❌ | final_answer | 2 | 1 | 7078 | 0 | 0 | 7078 | 1702 | 86.1% | 10.6s |
| core | skill-15 | 1 | ❌ | final_answer | 2 | 1 | 2540 | 0 | 0 | 2540 | 2540 | 0.0% | 9.1s |
| core | skill-15 | 2 | ❌ | final_answer | 2 | 1 | 2556 | 0 | 0 | 2556 | 1788 | 39.7% | 8.4s |
| core | skill-15 | 3 | ❌ | final_answer | 2 | 1 | 2534 | 0 | 0 | 2534 | 998 | 80.0% | 10.0s |
| core | eval-20 | 1 | ✅ | final_answer | 2 | 1 | 6878 | 0 | 0 | 6878 | 4190 | 41.5% | 7.8s |
| core | eval-20 | 2 | ✅ | final_answer | 2 | 1 | 6813 | 0 | 0 | 6813 | 4125 | 41.8% | 6.7s |
| core | eval-20 | 3 | ✅ | final_answer | 2 | 1 | 6857 | 0 | 0 | 6857 | 3913 | 45.5% | 6.5s |
| memory | memory-01/learn | 1 | ❌ | final_answer | 1 | 0 | 1916 | 0 | 1295 | 3211 | 2699 | 24.7% | 15.0s |
| memory | memory-01/recall | 1 | ✅ | final_answer | 2 | 1 | 3134 | 0 | 1132 | 4266 | 2474 | 45.8% | 10.0s |
| memory | memory-01/learn | 2 | ✅ | final_answer | 1 | 0 | 1829 | 0 | 1458 | 3287 | 1623 | 79.7% | 12.5s |
| memory | memory-01/recall | 2 | ✅ | final_answer | 2 | 1 | 3246 | 0 | 1108 | 4354 | 2434 | 48.0% | 8.3s |
| memory | memory-01/learn | 3 | ❌ | final_answer | 2 | 1 | 4653 | 0 | 1154 | 5807 | 1967 | 83.7% | 16.0s |
| memory | memory-01/recall | 3 | ❌ | final_answer | 1 | 0 | 1521 | 0 | 1173 | 2694 | 2182 | 24.7% | 8.0s |
| memory | memory-03/prefer | 1 | ✅ | final_answer | 2 | 1 | 3197 | 0 | 1403 | 4600 | 1528 | 81.7% | 11.8s |
| memory | memory-03/prefer | 2 | ✅ | final_answer | 2 | 1 | 3203 | 0 | 1379 | 4582 | 1382 | 85.1% | 11.2s |
| memory | memory-03/prefer | 3 | ✅ | final_answer | 2 | 1 | 3119 | 0 | 1232 | 4351 | 1279 | 82.7% | 10.3s |
| memory | memory-05/revise | 1 | ✅ | final_answer | 2 | 1 | 3799 | 0 | 2817 | 6616 | 4696 | 48.0% | 27.3s |
| memory | memory-05/revise | 2 | ✅ | final_answer | 2 | 1 | 3852 | 0 | 2468 | 6320 | 3248 | 75.1% | 26.3s |
| memory | memory-05/revise | 3 | ✅ | final_answer | 2 | 1 | 3960 | 0 | 5178 | 9138 | 5426 | 72.7% | 37.2s |
| learning | learning-04 | 1 | ✅ | completed | 0 | 0 | 2776 | 0 | 0 | 2776 | 2776 | 未知 | 7.1s |
| learning | learning-04 | 2 | ❌ | completed | 0 | 0 | 818 | 0 | 0 | 818 | 818 | 未知 | 1.3s |
| learning | learning-04 | 3 | ❌ | completed | 0 | 0 | 815 | 0 | 0 | 815 | 815 | 未知 | 1.2s |
| learning | learning-05b | 1 | ✅ | completed | 0 | 0 | 3290 | 0 | 0 | 3290 | 3290 | 未知 | 7.7s |
| learning | learning-05b | 2 | ✅ | completed | 0 | 0 | 3335 | 0 | 0 | 3335 | 3335 | 未知 | 7.7s |
| learning | learning-05b | 3 | ✅ | completed | 0 | 0 | 3342 | 0 | 0 | 3342 | 3342 | 未知 | 8.0s |

## 失败归因

### core · skill-03 · run#3
- [answer] missing_keypoints=['WAL']; answer=''
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-lt9rj0a1/core/skill-03/run-3/trace.json`

### core · skill-04 · run#1
- [tools] called=['read_file', 'read_file', 'read_file', 'read_file', 'write_file', 'skill_read', 'read_file', 'write_file']; count_failures=['skill_read=1 期望 2']; order=['read_file', 'read_file', 'read_file', 'read_file', 'write_file', 'skill_read', 'read_file', 'write_file'] 未包含有序序列 ['skill_read', 'skill_read']; failed_results=['read_file: Tool execution failed: FileNotFoundError: file does not exist: bug.py', 'read_file: Tool execution failed: FileNotFoundError: file does not exist: bug.py', 'read_file: Tool execution failed: FileNotFoundError: file does not exist: bug.py']
- [skill] activated=['code-review']; missing_activated=['debug-python']
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-lt9rj0a1/core/skill-04/run-1/trace.json`

### core · skill-04 · run#2
- [tools] called=['read_file', 'skill_read', 'read_file', 'read_file', 'write_file', 'read_file']; count_failures=['skill_read=1 期望 2']; order=['read_file', 'skill_read', 'read_file', 'read_file', 'write_file', 'read_file'] 未包含有序序列 ['skill_read', 'skill_read']; failed_results=['read_file: Tool execution failed: FileNotFoundError: file does not exist: bug.py', 'read_file: Tool execution failed: FileNotFoundError: file does not exist: bug.py']
- [skill] activated=['code-review']; missing_activated=['debug-python']
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-lt9rj0a1/core/skill-04/run-2/trace.json`

### core · skill-04 · run#3
- [tools] called=['read_file', 'read_file', 'read_file', 'write_file', 'skill_read', 'read_file']; count_failures=['skill_read=1 期望 2']; order=['read_file', 'read_file', 'read_file', 'write_file', 'skill_read', 'read_file'] 未包含有序序列 ['skill_read', 'skill_read']; failed_results=['read_file: Tool execution failed: FileNotFoundError: file does not exist: bug.py', 'read_file: Tool execution failed: FileNotFoundError: file does not exist: bug.py']
- [skill] activated=['code-review']; missing_activated=['debug-python']
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-lt9rj0a1/core/skill-04/run-3/trace.json`

### core · skill-06 · run#3
- [skill] activated=[]; missing_activation_failed=['write-notes']
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-lt9rj0a1/core/skill-06/run-3/trace.json`

### core · skill-15 · run#1
- [skill] activated=['debug-python']; active skill 未在压缩后保留
- [compaction] compaction_events=[]
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-lt9rj0a1/core/skill-15/run-1/trace.json`

### core · skill-15 · run#2
- [skill] activated=['debug-python']; active skill 未在压缩后保留
- [answer] missing_keypoints=['int', 'ValueError']; answer=''
- [compaction] compaction_events=[]
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-lt9rj0a1/core/skill-15/run-2/trace.json`

### core · skill-15 · run#3
- [skill] activated=['debug-python']; active skill 未在压缩后保留
- [compaction] compaction_events=[]
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-lt9rj0a1/core/skill-15/run-3/trace.json`

### memory · memory-01/learn · run#1
- [stored_memory] content_missing=向量
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-lt9rj0a1/memory/memory-01/run-1/on/phase-learn/trace.json`

### memory · memory-01/learn · run#3
- [reflection_action] actual=none expected=create
- [reflection_mutation] actual=False expected=True
- [active_count] actual=0 expected=1
- [core] missing=[] forbidden=['Markdown', '向量数据库']
- [stored_memory] not_found=STORAGE_DECISION
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-lt9rj0a1/memory/memory-01/run-3/on/phase-learn/trace.json`

### memory · memory-01/recall · run#3
- [recall] reads=[] missing=['STORAGE_DECISION'] forbidden=[]
- [read_count] actual=0 expected=1
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-lt9rj0a1/memory/memory-01/run-3/on/phase-recall/trace.json`

### learning · learning-04 · run#2
- [learning] candidate_count=0 expected 1; expected names ['ci-cache-recovery'] not matched (actual: []); create_count=0 expected 1; pattern not detected (0 clusters or no overlap with expected tasks); action not create: []
- Pattern Mining：scanned=4, clusters=0
- Distillation：未调用

### learning · learning-04 · run#3
- [learning] candidate_count=0 expected 1; expected names ['ci-cache-recovery'] not matched (actual: []); create_count=0 expected 1; pattern not detected (0 clusters or no overlap with expected tasks); action not create: []
- Pattern Mining：scanned=4, clusters=0
- Distillation：未调用
