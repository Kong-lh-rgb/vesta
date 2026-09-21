"""Token 估算误差校准：对比 Trace 中的请求前估算与 Provider 实际 Usage。

数据源：本地 ``.vesta/vesta.db`` 的 agent_events。
每一步模型请求会产生：
- ``model_started``：``estimated_input_tokens``（请求前的估算值）
- ``model_completed``：``usage.input_tokens``（Provider 返回的实际值）

按 Provider 统计 估算/实际 比值，输出 P50 / P95 / 最大低估比例，
用于校准 ``app/context/tokens.py`` 的模型族系数。

用法：
    .venv/bin/python scripts/calibrate_tokens.py [数据库路径]
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / ".vesta" / "vesta.db"


def _load_pairs(database: Path) -> list[tuple[str, str, int, int]]:
    """按 (run_id, step) 配对估算值与实际 input_tokens。"""

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT run_id, payload_json FROM agent_events "
        "WHERE type IN ('model_started', 'model_completed') "
        "ORDER BY run_id, sequence"
    ).fetchall()
    connection.close()

    started: dict[tuple[str, int | None], tuple[str, int]] = {}
    pairs: list[tuple[str, str, int, int]] = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        key = (row["run_id"], payload.get("step"))
        provider = payload.get("provider") or "unknown"
        if row["payload_json"] and '"model_started"' in row["payload_json"]:
            # type 字段不在 exclude_none payload 里时按事件顺序兜底。
            pass
        if _event_type(row["payload_json"]) == "model_started":
            estimated = payload.get("estimated_input_tokens")
            if isinstance(estimated, int):
                started[key] = (provider, estimated)
        else:
            usage = payload.get("usage") or {}
            actual = usage.get("input_tokens")
            previous = started.pop(key, None)
            if previous and isinstance(actual, int) and actual > 0:
                pairs.append((previous[0], row["run_id"], previous[1], actual))
    return pairs


def _event_type(payload_json: str) -> str:
    """Trace payload 不含 type 字段；按字段特征区分 started/completed。"""

    payload = json.loads(payload_json)
    if "estimated_input_tokens" in payload:
        return "model_started"
    return "model_completed"


def _percentile(values: list[float], percent: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(percent * (len(ordered) - 1)))))
    return ordered[index]


def main() -> None:
    database = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    if not database.exists():
        print(f"数据库不存在：{database}")
        return
    pairs = _load_pairs(database)
    if not pairs:
        print("没有可配对的 model_started/model_completed 事件。")
        return

    by_provider: dict[str, list[float]] = defaultdict(list)
    underestimates: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for provider, run_id, estimated, actual in pairs:
        ratio = estimated / actual
        by_provider[provider].append(ratio)
        if ratio < 1.0:
            underestimates[provider].append((run_id, ratio))

    print(f"数据库：{database}")
    print(f"总样本：{len(pairs)}（估算/实际 比值，<1 表示低估）\n")
    print(f"{'provider':<12} {'样本':>5} {'P50':>7} {'P95':>7} {'最小':>7}  说明")
    for provider in sorted(by_provider):
        ratios = by_provider[provider]
        p50 = _percentile(ratios, 0.50)
        p95 = _percentile(ratios, 0.95)
        minimum = min(ratios)
        note = (
            "存在低估，建议上调系数"
            if minimum < 0.95
            else "覆盖充分（无显著低估）"
        )
        print(
            f"{provider:<12} {len(ratios):>5} {p50:>7.2f} {p95:>7.2f} "
            f"{minimum:>7.2f}  {note}"
        )
        for run_id, ratio in sorted(underestimates[provider], key=lambda x: x[1])[:3]:
            print(f"    低估样本 run={run_id[:8]} ratio={ratio:.2f}")
    print(
        "\n说明：ratio = 估算/实际。P95 < 1 表示常态化低估；"
        "系数建议取 1/P95 起步后再结合安全余量复核。"
    )


if __name__ == "__main__":
    main()
