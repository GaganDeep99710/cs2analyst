"""diagnose4 — ADR via authoritative post-hit health field. Target 96.2."""
import sys
from pathlib import Path
from demoparser2 import DemoParser

TARGET = "c0ldrsg"


def real_round_bounds(p):
    match_start = int(p.parse_event("begin_new_match")["tick"].min())
    fe = sorted(p.parse_event("round_freeze_end")["tick"].tolist())
    starts = [t for t in fe if t > match_start]
    return [(s, starts[i + 1] if i + 1 < len(starts) else 10**12)
            for i, s in enumerate(starts)]


def round_of(tick, bounds):
    for i, (s, e) in enumerate(bounds):
        if s <= tick < e:
            return i
    return None


def main(demo_path):
    p = DemoParser(str(Path(demo_path)))
    bounds = real_round_bounds(p)
    n = len(bounds)

    hurt = p.parse_event("player_hurt", player=["team_num"])
    hurt = hurt.copy()
    hurt["rnd"] = hurt["tick"].apply(lambda t: round_of(t, bounds))
    hurt = hurt[hurt["rnd"].notna()].sort_values("tick")

    # Authoritative: victim 'health' is HP AFTER the hit. Real HP removed by
    # a hit = prev_health(victim) - health_after. Naturally accounts for
    # overkill AND prior damage from any attacker AND armor. Credit only
    # c0ldrsg's non-team hits.
    prev = {}
    target_dmg = 0.0
    for _, r in hurt.iterrows():
        key = (r["rnd"], r["user_name"])
        before = prev.get(key, 100.0)
        after = float(r["health"])
        removed = max(before - after, 0.0)
        prev[key] = after
        if (r["attacker_name"] == TARGET
                and r["attacker_name"] != r["user_name"]):
            same_team = (
                {"attacker_team_num", "user_team_num"}.issubset(hurt.columns)
                and r["attacker_team_num"] == r["user_team_num"]
            )
            if not same_team:
                target_dmg += removed

    print(f"real rounds: {n}")
    print(f"ADR (authoritative health-diff) = {target_dmg / n:.1f}  "
          f"<- target 96.2")

    # assist detail: is the 8th a flash assist?
    dd = p.parse_event("player_death")
    print(f"\nplayer_death columns: {list(dd.columns)}")
    ma = dd[dd["assister_name"] == TARGET].copy()
    ma["rnd"] = ma["tick"].apply(lambda t: round_of(t, bounds))
    ma = ma[ma["rnd"].notna()]
    flash_col = next((c for c in dd.columns if "flash" in c.lower()), None)
    print(f"total real-round assists: {len(ma)}")
    if flash_col:
        fa = ma[ma[flash_col] == True]  # noqa: E712
        print(f"  flash-assist column '{flash_col}': "
              f"{ma[flash_col].tolist()}")
        print(f"  regular (non-flash) assists: {len(ma) - len(fa)} "
              f"<- FACEIT shows 7 regular + flash separately?")


if __name__ == "__main__":
    main(sys.argv[1])
