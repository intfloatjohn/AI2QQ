#!/usr/bin/env python3
"""Summarises the model usage recorded by autonomous_agent.py in usage_stats/usage-YYYY-MM-DD.jsonl.

    python3 usage_report.py                  # everything recorded
    python3 usage_report.py --days 3         # the last 3 days
    python3 usage_report.py --price-in 0.30 --price-out 2.50 --price-cached 0.03
                                             # estimate cost (USD per 1M tokens)

Only numbers are recorded (tokens, timings, counts), never message content.
"""
import argparse
import datetime
import glob
import json
import os
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USAGE_DIR = os.path.join(BASE_DIR, "usage_stats")

PURPOSE_NAMES = {
    "chat_master": "Chat: Master (private)",
    "chat_group": "Chat: groups",
    "chat_friend": "Chat: friends (private)",
    "memory_compact": "Memory: AutoCompact",
    "memory_tidy": "Memory: tidy-up",
    "group_glance": "Group glance",
    "qzone_react": "Qzone: comment/like",
    "qzone_post": "Qzone: own post",
    "background": "Other background",
}


def load(days: int = 0) -> list:
    files = sorted(glob.glob(os.path.join(USAGE_DIR, "usage-*.jsonl")))
    if days > 0:
        cutoff = (datetime.date.today() - datetime.timedelta(days=days - 1)).isoformat()
        files = [f for f in files if os.path.basename(f)[6:16] >= cutoff]
    rows = []
    for path in files:
        day = os.path.basename(path)[6:16]
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                    r["_day"] = day
                    rows.append(r)
                except ValueError:
                    continue
    return rows


def fmt(n) -> str:
    n = float(n)
    if n >= 1e6:
        return f"{n / 1e6:.2f}M"
    if n >= 1e4:
        return f"{n / 1e3:.1f}k"
    return f"{int(n)}"


def pct(a, b) -> str:
    return f"{100 * a / b:.0f}%" if b else "-"


def cost_of(r: dict, price_in: float, price_out: float, price_cached: float) -> float:
    if r.get("cost") is not None and not (price_in or price_out):
        try:
            return float(r["cost"])
        except (TypeError, ValueError):
            pass
    cached = r.get("cached_tokens", 0)
    uncached = max(0, r.get("prompt_tokens", 0) - cached)
    pc = price_cached if price_cached else price_in
    return (uncached * price_in + cached * pc + r.get("completion_tokens", 0) * price_out) / 1e6


def table(headers: list, rows: list):
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h)) for i, h in enumerate(headers)]
    line = "  ".join(str(h).ljust(w) if i == 0 else str(h).rjust(w) for i, (h, w) in enumerate(zip(headers, widths)))
    print(line)
    print("-" * len(line))
    for r in rows:
        print("  ".join(str(c).ljust(w) if i == 0 else str(c).rjust(w) for i, (c, w) in enumerate(zip(r, widths))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=0, help="only the last N days (default: everything)")
    ap.add_argument("--price-in", type=float, default=0.0, help="USD per 1M input tokens")
    ap.add_argument("--price-out", type=float, default=0.0, help="USD per 1M output tokens (thinking included)")
    ap.add_argument("--price-cached", type=float, default=0.0, help="USD per 1M cached input tokens (default: same as input)")
    args = ap.parse_args()

    rows = load(args.days)
    if not rows:
        print(f"No usage recorded yet in {USAGE_DIR}.")
        return
    has_price = bool(args.price_in or args.price_out)
    has_cost = has_price or any(r.get("cost") is not None for r in rows)
    days = sorted({r["_day"] for r in rows})
    print(f"Model usage {days[0]} .. {days[-1]}  ({len(days)} day(s), {len(rows)} calls)")
    if not has_cost:
        print("(Add --price-in/--price-out to estimate cost; the provider did not report one.)")
    print()

    # 1. By purpose
    agg = defaultdict(lambda: defaultdict(float))
    for r in rows:
        a = agg[r.get("purpose", "?")]
        a["calls"] += 1
        a["failed"] += 0 if r.get("ok") else 1
        a["retries"] += 1 if r.get("attempt", 0) > 0 or r.get("note") else 0
        a["superseded"] += 1 if r.get("superseded") else 0
        a["prompt"] += r.get("prompt_tokens", 0)
        a["cached"] += r.get("cached_tokens", 0)
        a["completion"] += r.get("completion_tokens", 0)
        a["reasoning"] += r.get("reasoning_tokens", 0)
        a["images"] += r.get("images", 0)
        a["sys_changed"] += 1 if r.get("system_changed") else 0
        a["latency"] += r.get("latency_ms", 0)
        a["tool_rounds"] += 1 if r.get("iteration", 0) > 0 else 0
        a["cost"] += cost_of(r, args.price_in, args.price_out, args.price_cached)
    total = defaultdict(float)
    out = []
    for purpose, a in sorted(agg.items(), key=lambda kv: -(kv[1]["prompt"] + kv[1]["completion"])):
        for k, v in a.items():
            total[k] += v
        out.append([PURPOSE_NAMES.get(purpose, purpose), int(a["calls"]), int(a["failed"]), int(a["retries"]),
                    int(a["superseded"]), int(a["tool_rounds"]), fmt(a["prompt"] / max(1, a["calls"])), fmt(a["prompt"]),
                    pct(a["cached"], a["prompt"]), fmt(a["completion"]), pct(a["reasoning"], a["completion"]),
                    int(a["images"]), pct(a["sys_changed"], a["calls"]), f"{a['latency'] / max(1, a['calls']) / 1000:.1f}s"]
                   + ([f"${a['cost']:.4f}"] if has_cost else []))
    out.append(["TOTAL", int(total["calls"]), int(total["failed"]), int(total["retries"]), int(total["superseded"]),
                int(total["tool_rounds"]), fmt(total["prompt"] / max(1, total["calls"])), fmt(total["prompt"]),
                pct(total["cached"], total["prompt"]), fmt(total["completion"]), pct(total["reasoning"], total["completion"]),
                int(total["images"]), pct(total["sys_changed"], total["calls"]),
                f"{total['latency'] / max(1, total['calls']) / 1000:.1f}s"] + ([f"${total['cost']:.4f}"] if has_cost else []))
    table(["Purpose", "Calls", "Failed", "Retry", "Wasted", "ToolRnd", "In/call", "Input", "Cached", "Output",
           "Thinking", "Images", "SysChg", "Avg time"] + (["Cost"] if has_cost else []), out)
    print()
    print("Wasted  = reply thrown away because a newer message arrived (cost paid, nothing sent).")
    print("ToolRnd = extra rounds after a tool call (each resends the whole conversation).")
    print("Cached  = share of input billed at the cheaper cached rate. SysChg = calls whose system prompt")
    print("          changed since the previous call in that chat (this prevents caching).")
    print("Thinking = share of output tokens spent on hidden reasoning.")
    print()

    # 2. By day
    per_day = defaultdict(lambda: defaultdict(float))
    for r in rows:
        d = per_day[r["_day"]]
        d["calls"] += 1
        d["prompt"] += r.get("prompt_tokens", 0)
        d["cached"] += r.get("cached_tokens", 0)
        d["completion"] += r.get("completion_tokens", 0)
        d["cost"] += cost_of(r, args.price_in, args.price_out, args.price_cached)
    table(["Day", "Calls", "Input", "Cached", "Output"] + (["Cost"] if has_cost else []),
          [[day, int(d["calls"]), fmt(d["prompt"]), pct(d["cached"], d["prompt"]), fmt(d["completion"])]
           + ([f"${d['cost']:.4f}"] if has_cost else []) for day, d in sorted(per_day.items())])
    print()

    # 3. Heaviest chats
    per_chat = defaultdict(lambda: [0, 0.0])
    for r in rows:
        c = per_chat[r.get("chat", "?")]
        c[0] += 1
        c[1] += r.get("prompt_tokens", 0) + r.get("completion_tokens", 0)
    top = sorted(per_chat.items(), key=lambda kv: -kv[1][1])[:8]
    table(["Chat", "Calls", "Tokens"], [[k, v[0], fmt(v[1])] for k, v in top])
    print()

    # 4. What a typical chat call carries
    chats = [r for r in rows if str(r.get("purpose", "")).startswith("chat_") and r.get("ok")]
    if chats:
        n = len(chats)
        print("Average chat call: "
              f"system prompt {fmt(sum(r.get('system_chars', 0) for r in chats) / n)} chars, "
              f"tool list {fmt(sum(r.get('tools_chars', 0) for r in chats) / n)} chars, "
              f"{sum(r.get('messages', 0) for r in chats) / n:.0f} messages, "
              f"{sum(r.get('images', 0) for r in chats) / n:.2f} images")


if __name__ == "__main__":
    main()
