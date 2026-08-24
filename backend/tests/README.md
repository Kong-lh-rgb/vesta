# Backend 测试目录

本目录先按“执行语义”区分离线测试与真实模型评测，再在各自目录内按领域组织。

```text
tests/
├── offline/       pytest 默认收集的离线测试
├── fixtures/      多个测试共享的固定夹具与假服务
└── eval_legacy/   已冻结的 Eval V1 实现、场景和历史报告
```

## offline

`offline/` 按 Agent、Context、Memory、Task、Computer 等生产领域分组。这里的测试不得调用
真实模型 API 或依赖外部服务，适合本地回归和 CI。

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/python -m pytest tests/offline/memory
.venv/bin/python -m pytest tests/offline/computer
```

## fixtures

`fixtures/` 只保存可重复、无副作用的测试夹具，例如 Fake MCP Server 和 Fake Computer
Helper。不要把真实运行数据、临时输出或模型报告放进这里。

## eval_legacy

`eval_legacy/` 是现有 Eval V1 的冻结区，保留 Agent Runtime、Memory 和 Skill Learning
场景及其历史证据。目录名用于明确：它可以继续复现和维护，但不再作为下一代 Eval 设计的
默认落点。

Eval Harness 自检仍属于离线 pytest：

```bash
.venv/bin/python -m pytest tests/eval_legacy/tests
```

真实模型 Eval 必须显式运行，可能产生 API 成本：

```bash
.venv/bin/python -m tests.eval_legacy.run_suite --help
.venv/bin/python -m tests.eval_legacy.run_live --help
.venv/bin/python -m tests.eval_legacy.memory.run_live --help
```

后续重新设计 Eval V2 时使用新的 `tests/eval/`，不要继续向 `eval_legacy/` 堆叠新抽象。
