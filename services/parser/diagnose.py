"""
diagnose.py — figure out why our numbers disagree with FACEIT.

FACEIT (match d3c95979, c0ldrsg): ADR 96.2, K/D/A 17/13/7, score 13-6 (19 rds).
Our tool:                          ADR 115.8, K/D/A 17/14/8, 20 decisive rounds.

Three suspects, three probes:
  1. one phantom round inflating round count + deaths + assists
  2. overkill damage inflating ADR (115 AWP vs a 100hp player counts 115 not 100)
  3. warmup leakage
"""

import sys
from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_rows", 60)

TARGET = "c0ldrsg"


def main(demo_path: str) -> None:
    parser = DemoParser(str(Path(demo_path)))

    # ---- PROBE 1: every round_end, look for a phantom / duplicate --------
    print("=" * 70)
    print("PROBE 1 — round_end events (looking for the extra round)")
    print("=" * 70)
    re = parser.parse_event(
        "round_end", other=["total_rounds_played", "is_warmup_period"]
    )
    cols = [c for c in ["tick", "round", "total_rounds_played", "winner",
                        "reason", "is_warmup_period"] if c in re.columns]
    print(re[cols].to_string(index=False))
    print(f"\ntotal round_end rows: {len(re)}")
    print(f"winner in (T,CT):     {len(re[re['winner'].isin(['T','CT'])])}")

    # ---- PROBE 2: damage — raw vs overkill-capped -----------------------
    print("\n" + "=" * 70)
    print("PROBE 2 — damage for c0ldrsg: raw vs HP-capped")
    print("=" * 70)
    hurt = parser.parse_event(
        "player_hurt",
        player=["team_num"],
        other=["total_rounds_played", "is_warmup_period"],
    )
    print("player_hurt columns:", list(hurt.columns))

    h = hurt[hurt["attacker_name"] == TARGET].copy()
    h = h[h["attacker_name"] != h["user_name"]]  # no self
    if "is_warmup_period" in h.columns:
        warm = h[h["is_warmup_period"].fillna(False)]
        print(f"\nwarmup damage rows by {TARGET}: {len(warm)} "
              f"(dmg={warm['dmg_health'].sum() if len(warm) else 0})")
        h = h[~h["is_warmup_period"].fillna(False)]

    raw = h["dmg_health"].sum()
    print(f"\nRAW dmg_health sum (no cap):        {raw}")
    print(f"max single dmg_health event:        {h['dmg_health'].max()}")
    over100 = h[h["dmg_health"] > 100]
    print(f"events with dmg_health > 100:       {len(over100)}")

    # HP-capped: reconstruct each victim's HP per round, cap each hit.
    if "health" in h.columns:
        print("\nsample rows (victim health AFTER hit):")
        print(h[["total_rounds_played", "user_name", "dmg_health",
                 "health", "hitgroup"]].head(10).to_string(index=False))

    capped_total = 0
    hh = h.sort_values("tick")
    round_col = ("total_rounds_played"
                 if "total_rounds_played" in hh.columns else None)
    hp: dict[tuple, float] = {}
    for _, row in hh.iterrows():
        rnd = row[round_col] if round_col else 0
        key = (rnd, row["user_name"])
        cur = hp.get(key, 100.0)
        applied = min(float(row["dmg_health"]), max(cur, 0.0))
        capped_total += applied
        hp[key] = cur - applied
    print(f"\nHP-CAPPED damage total:             {capped_total:.0f}")

    for n in (20, 19):
        print(f"  ADR raw    / {n} rds = {raw / n:6.1f}")
        print(f"  ADR capped / {n} rds = {capped_total / n:6.1f}")

    # ---- PROBE 3: deaths & assists per round for c0ldrsg ----------------
    print("\n" + "=" * 70)
    print("PROBE 3 — c0ldrsg deaths & assists by round")
    print("=" * 70)
    dd = parser.parse_event(
        "player_death",
        other=["total_rounds_played", "is_warmup_period"],
    )
    if "is_warmup_period" in dd.columns:
        w = dd[dd["is_warmup_period"].fillna(False)]
        print(f"warmup deaths total: {len(w)}")
        dd = dd[~dd["is_warmup_period"].fillna(False)]

    my_deaths = dd[dd["user_name"] == TARGET]
    print(f"\n{TARGET} deaths: {len(my_deaths)}  by round: "
          f"{sorted(my_deaths['total_rounds_played'].tolist())}")
    my_ass = dd[dd.get("assister_name") == TARGET]
    print(f"{TARGET} assists: {len(my_ass)} by round: "
          f"{sorted(my_ass['total_rounds_played'].tolist())}")
    print(f"max total_rounds_played seen in deaths: "
          f"{dd['total_rounds_played'].max()}")


if __name__ == "__main__":
    main(sys.argv[1])
