"""diagnose2 — nail the phantom round. Knife round at start, or a mid-match dup?"""
import sys
from pathlib import Path
from demoparser2 import DemoParser

TARGET = "c0ldrsg"
TICK = 64  # will correct from header


def t(tick, base):
    return f"{tick} (~{tick / base:.0f}s)"


def main(demo_path):
    p = DemoParser(str(Path(demo_path)))
    # FACEIT is 128-tick; confirm via playback if present
    base = 128

    print("== begin_new_match ==")
    try:
        bm = p.parse_event("begin_new_match")
        print(bm[["tick"]].to_string(index=False) if len(bm) else "none")
    except Exception as e:
        print("err", e)

    print("\n== round_freeze_end ticks (start of each live round) ==")
    fe = p.parse_event("round_freeze_end")
    fe_ticks = sorted(fe["tick"].tolist())
    print(f"count={len(fe_ticks)}")
    print([t(x, base) for x in fe_ticks])

    print("\n== round_officially_ended ticks ==")
    oe = p.parse_event("round_officially_ended")
    oe_ticks = sorted(oe["tick"].tolist())
    print(f"count={len(oe_ticks)}")

    print("\n== bomb_planted / defused / exploded counts (real-round sanity) ==")
    for ev in ("bomb_planted", "bomb_exploded"):
        try:
            print(f"  {ev}: {len(p.parse_event(ev))}")
        except Exception as e:
            print(f"  {ev}: err {e}")

    print(f"\n== {TARGET} death ticks ==")
    dd = p.parse_event("player_death", other=["total_rounds_played"])
    md = dd[dd["user_name"] == TARGET].sort_values("tick")
    for _, r in md.iterrows():
        print(f"  tick {t(r['tick'], base):>16}  trp={r['total_rounds_played']}"
              f"  killer={r['attacker_name']}  weap={r['weapon']}")

    print(f"\n== the two trp=4 deaths (dup or two real rounds?) ==")
    d4 = dd[(dd["total_rounds_played"] == 4)].sort_values("tick")
    cols = [c for c in ["tick", "user_name", "attacker_name", "weapon"]
            if c in d4.columns]
    print(d4[cols].to_string(index=False))
    print("\nfreeze_end ticks bracketing those deaths tell us if they're "
          "in the same live round (dup) or different rounds.")


if __name__ == "__main__":
    main(sys.argv[1])
