# Vesta Agent 综合评测报告

## 汇总

| 指标 | 值 |
| --- | --- |
| 请求重复次数 | 3 |
| 预期样本数 | 33 |
| 实际样本数 | 33 |
| 样本完整性 | ✅ 完整 |
| 通过数 | 25 |
| 样本通过率 | 75.8% |
| 稳定通过率 | 72.7% |
| 安全场景通过率 | 100.0% |
| 平均 Steps | 1.5 |
| 平均模型调用 | 2.2 |
| 平均可计费 Token | 3184 |
| P95 可计费 Token | 9067 |
| 平均缓存命中率 | 63.2% |
| 平均耗时 | 17.7s |

## 运行信息

- Provider / Model：deepseek / deepseek-v4-flash
- Suites：core, memory, learning
- Tier：regression
- Git Commit：-
- Scenario Digest：e8fedb4592b2af8eae1347c9980cd58b63fd60a9c3c5c56385f27dbfd111fa94
- 生成时间：2026-08-23T12:52:15.662280+00:00
- 运行现场：/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-v3aec519

## 样本完整性

所有稳定性键均包含完整的重复运行样本。

| 稳定性样本 | 期望 Run | 实际 Run | 完整 |
| --- | --- | --- | --- |
| core/eval-05 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/eval-08 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/eval-10 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/eval-27 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/skill-03 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/skill-14 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| core/skill-15 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| learning/learning-05a (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| learning/learning-09 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| learning/learning-10 (on) | [1, 2, 3] | [1, 2, 3] | ✅ |
| memory/memory-03/prefer (on) | [1, 2, 3] | [1, 2, 3] | ✅ |

## 分组结果

| Suite / Group | 通过 | 样本 | 通过率 |
| --- | --- | --- | --- |
| core / basic | 6 | 6 | 100.0% |
| core / context | 1 | 3 | 33.3% |
| core / safety | 3 | 3 | 100.0% |
| core / skill | 9 | 9 | 100.0% |
| learning / learning | 6 | 9 | 66.7% |
| memory / memory | 0 | 3 | 0.0% |

## 分样本

| Suite | 场景 / Phase | Run | 结果 | Stop | Steps | Tools | Main | Summary | Reflection | Total | Chargeable | Cache | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core | eval-08 | 1 | ✅ | final_answer | 1 | 0 | 1085 | 0 | 0 | 1085 | 1085 | 0.0% | 9.8s |
| core | eval-08 | 2 | ✅ | final_answer | 1 | 0 | 1245 | 0 | 0 | 1245 | 861 | 95.5% | 11.2s |
| core | eval-08 | 3 | ✅ | final_answer | 1 | 0 | 1171 | 0 | 0 | 1171 | 787 | 95.5% | 10.0s |
| core | eval-10 | 1 | ✅ | final_answer | 1 | 0 | 1391 | 0 | 0 | 1391 | 1007 | 40.5% | 6.1s |
| core | eval-10 | 2 | ✅ | final_answer | 1 | 0 | 1341 | 0 | 0 | 1341 | 445 | 94.5% | 5.5s |
| core | eval-10 | 3 | ✅ | final_answer | 1 | 0 | 1356 | 0 | 0 | 1356 | 460 | 94.5% | 6.0s |
| core | eval-05 | 1 | ✅ | final_answer | 2 | 0 | 3967 | 1196 | 0 | 5163 | 3883 | 42.8% | 26.4s |
| core | eval-05 | 2 | ❌ | context_error | 1 | 0 | 1352 | 1352 | 0 | 2704 | 656 | 98.0% | 6.1s |
| core | eval-05 | 3 | ❌ | context_error | 2 | 0 | 1439 | 1271 | 0 | 2710 | 1430 | 61.4% | 7.9s |
| core | eval-27 | 1 | ✅ | final_answer | 1 | 0 | 3419 | 0 | 0 | 3419 | 3035 | 12.7% | 6.3s |
| core | eval-27 | 2 | ✅ | final_answer | 1 | 0 | 3357 | 0 | 0 | 3357 | 413 | 97.5% | 4.9s |
| core | eval-27 | 3 | ✅ | final_answer | 1 | 0 | 3245 | 0 | 0 | 3245 | 301 | 97.5% | 5.0s |
| core | skill-03 | 1 | ✅ | final_answer | 3 | 2 | 8167 | 0 | 0 | 8167 | 5991 | 57.5% | 46.1s |
| core | skill-03 | 2 | ✅ | final_answer | 4 | 2 | 13425 | 0 | 0 | 13425 | 10481 | 58.3% | 81.4s |
| core | skill-03 | 3 | ✅ | final_answer | 4 | 2 | 12523 | 0 | 0 | 12523 | 9067 | 68.5% | 76.7s |
| core | skill-14 | 1 | ✅ | final_answer | 3 | 2 | 7083 | 0 | 0 | 7083 | 5035 | 58.2% | 42.1s |
| core | skill-14 | 2 | ✅ | final_answer | 3 | 2 | 7573 | 0 | 0 | 7573 | 5141 | 69.3% | 44.7s |
| core | skill-14 | 3 | ✅ | final_answer | 3 | 2 | 6882 | 0 | 0 | 6882 | 3938 | 83.9% | 38.0s |
| core | skill-15 | 1 | ✅ | final_answer | 2 | 2 | 3324 | 911 | 0 | 4235 | 2827 | 41.0% | 12.0s |
| core | skill-15 | 2 | ✅ | final_answer | 2 | 2 | 3333 | 902 | 0 | 4235 | 2827 | 41.0% | 15.6s |
| core | skill-15 | 3 | ✅ | final_answer | 2 | 2 | 3329 | 902 | 0 | 4231 | 2823 | 41.1% | 13.6s |
| memory | memory-03/prefer | 1 | ❌ | model_error | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 未知 | 4.6s |
| memory | memory-03/prefer | 2 | ❌ | final_answer | 4 | 3 | 9057 | 0 | 1859 | 10916 | 6564 | 43.9% | 26.4s |
| memory | memory-03/prefer | 3 | ❌ | final_answer | 3 | 2 | 6679 | 0 | 1618 | 8297 | 3689 | 59.8% | 15.6s |
| learning | learning-05a | 1 | ❌ | completed | 0 | 0 | 1021 | 0 | 0 | 1021 | 1021 | 未知 | 1.8s |
| learning | learning-05a | 2 | ❌ | completed | 0 | 0 | 1030 | 0 | 0 | 1030 | 1030 | 未知 | 2.1s |
| learning | learning-05a | 3 | ❌ | completed | 0 | 0 | 1022 | 0 | 0 | 1022 | 1022 | 未知 | 4.4s |
| learning | learning-09 | 1 | ✅ | completed | 0 | 0 | 2482 | 0 | 0 | 2482 | 2482 | 未知 | 5.1s |
| learning | learning-09 | 2 | ✅ | completed | 0 | 0 | 2488 | 0 | 0 | 2488 | 2488 | 未知 | 5.0s |
| learning | learning-09 | 3 | ✅ | completed | 0 | 0 | 2500 | 0 | 0 | 2500 | 2500 | 未知 | 4.3s |
| learning | learning-10 | 1 | ✅ | completed | 0 | 0 | 8110 | 0 | 0 | 8110 | 8110 | 未知 | 17.2s |
| learning | learning-10 | 2 | ✅ | completed | 0 | 0 | 6720 | 0 | 0 | 6720 | 6720 | 未知 | 11.3s |
| learning | learning-10 | 3 | ✅ | completed | 0 | 0 | 6947 | 0 | 0 | 6947 | 6947 | 未知 | 12.1s |

## 失败归因

### core · eval-05 · run#2
- [ran_ok] stop=context_error; expected=['final_answer']
- [answer] missing_keypoints=['效率提升']; answer='Agent stopped: context preparation failed: estimated input tokens (1937) exceed input budget (1804)'
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-v3aec519/core/eval-05/run-2/trace.json`

### core · eval-05 · run#3
- [ran_ok] stop=context_error; expected=['final_answer']
- [answer] missing_keypoints=['效率提升']; answer='Agent stopped: context preparation failed: estimated input tokens (1873) exceed input budget (1804)'
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-v3aec519/core/eval-05/run-3/trace.json`

### memory · memory-03/prefer · run#1
- [ran_ok] model_error
- [reflection_action] actual=None expected=none
- [core] missing=['先给结论', '解释原因'] forbidden=[]
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-v3aec519/memory/memory-03/run-1/on/phase-prefer/trace.json`

### memory · memory-03/prefer · run#2
- [core] missing=['先给结论'] forbidden=[]
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-v3aec519/memory/memory-03/run-2/on/phase-prefer/trace.json`

### memory · memory-03/prefer · run#3
- [core] missing=['先给结论'] forbidden=[]
- Trace：`/var/folders/pf/zby_ydbx0nj2f0krp_8wft140000gp/T/vesta-comprehensive-eval-v3aec519/memory/memory-03/run-3/on/phase-prefer/trace.json`

### learning · learning-05a · run#1
- [learning] pattern not detected (0 clusters or no overlap with expected tasks)
- Pattern Mining：scanned=4, clusters=0
- Pattern Mining raw_output（报告预览）：
```json
"{\"clusters\": []}"
```
- Distillation：未调用

### learning · learning-05a · run#2
- [learning] pattern not detected (0 clusters or no overlap with expected tasks)
- Pattern Mining：scanned=4, clusters=0
- Pattern Mining raw_output（报告预览）：
```json
"{\"clusters\":[]}"
```
- Distillation：未调用

### learning · learning-05a · run#3
- [learning] pattern not detected (0 clusters or no overlap with expected tasks)
- Pattern Mining：scanned=4, clusters=0
- Pattern Mining raw_output（报告预览）：
```json
"{\"clusters\": []}"
```
- Distillation：未调用
