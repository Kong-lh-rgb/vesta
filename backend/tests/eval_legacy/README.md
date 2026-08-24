# Eval V1（冻结区）

这里保存 Vesta 已有的 Eval V1。它的价值是保留可复现的场景、历史结果和优化证据，而不是
宣称一个综合通过率可以完整代表 Agent 智能水平。

```text
eval_legacy/
├── run_suite.py          Core / Memory / Learning 综合入口
├── run_live.py           Agent Runtime Live Eval
├── run_learning_live.py  Skill Learning Live Eval
├── memory/               长期记忆多阶段 Eval
├── scenarios/            Runtime 与 Learning YAML 场景
├── tests/                Harness 自检，不调用真实 API
└── reports/
    ├── baselines/        可机器比较的正式 Baseline
    ├── comprehensive/    综合评测运行目录
    └── historical/       旧版 Runtime / Memory / Learning 报告
```

## 使用边界

- `tests/` 验证加载、Harness、断言和报告机制本身，属于离线测试。
- `run_*.py` 才会调用真实模型，必须由开发者显式执行。
- 历史报告使用过不同题集、重复次数和断言版本，不能只按通过率直接横向排名。
- `94.1%` 等数字表示当时题集与断言契约的通过率，不等于开放问题上的智能准确率。
- 新的语义评测、LLM Judge 或人工复核体系应进入未来的 `tests/eval/`，避免继续修改历史口径。

## 常用命令

```bash
cd backend

# 只验证 Eval Harness，不产生 API 成本
.venv/bin/python -m pytest tests/eval_legacy/tests

# 查看综合、Runtime、Memory Live Eval 参数
.venv/bin/python -m tests.eval_legacy.run_suite --help
.venv/bin/python -m tests.eval_legacy.run_live --help
.venv/bin/python -m tests.eval_legacy.memory.run_live --help
```

报告演进和各批次可比性见 [reports/README.md](reports/README.md)。
