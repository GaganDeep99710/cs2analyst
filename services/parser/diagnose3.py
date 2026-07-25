"""diagnose3 — the corrected round model. Target: ADR 96.2, D 13, A 7."""
import sys
from pathlib import Path
from demoparser2 import DemoParser

TARGET = "c0ldrsg"


def real_round_bounds(p):
    """Real rounds = freeze_end ticks after begin_new_match.
    Returns list of (start_tick, end_tick) intervals, one per real round."""
    bm = p.parse_event("begin_new_match")
    match_start = int(bm["tick"].min())
    fe = sorted(p.parse_event("round_freeze_end")["tick"].tolist())
    starts = [t for t in fe if t > match_start]
    bounds = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else 10**12
        bounds.append((s, e))
    return match_start, bounds


def round_of(tick, bounds):
    for i, (s, e) in enumerate(bounds):
        if s <= tick < e:
            return i
    return None  # before first real round = warmup/knife


def main(demo_path):
    p = DemoParser(str(Path(demo_path)))
    match_start, bounds = real_round_bounds(p)
    n = len(bounds)
    print(f"begin_new_match tick: {match_start}")
    print(f"REAL ROUNDS: {n}   (FACEIT score 13-6 = 19)\n")

    # ---- ADR: HP-capped damage, only real rounds ------------------------
    hurt = p.parse_event("player_hurt", player=["team_num"])
    h = hurt[(hurt["attacker_name"] == TARGET)
             & (hurt["attacker_name"] != hurt["user_name"])].copy()
    if {"attacker_team_num", "user_team_num"}.issubset(h.columns):
        h = h[h["attacker_team_num"] != h["user_team_num"]]
    h["rnd"] = h["tick"].apply(lambda t: round_of(t, bounds))
    pre = h[h["rnd"].isna()]
    h = h[h["rnd"].notna()]
    print(f"dropped pre-match damage rows: {len(pre)} "
          f"(raw {pre['dmg_health'].sum() if len(pre) else 0})")

    # cap each hit at victim's remaining HP within its round
    capped = 0.0
    hp = {}
    for _, r in h.sort_values("tick").iterrows():
        key = (r["rnd"], r["user_name"])
        cur = hp.get(key, 100.0)
        applied = min(float(r["dmg_health"]), max(cur, 0.0))
        capped += applied
        hp[key] = cur - applied
    raw = h["dmg_health"].sum()
    print(f"\nADR raw    = {raw / n:.1f}")
    print(f"ADR capped = {capped / n:.1f}   <- target 96.2")

    # ---- deaths (real rounds, split out suicides) -----------------------
    dd = p.parse_event("player_death")
    md = dd[dd["user_name"] == TARGET].copy()
    md["rnd"] = md["tick"].apply(lambda t: round_of(t, bounds))
    md = md[md["rnd"].notna()]
    suicides = md[md["attacker_name"] == TARGET]
    print(f"\ndeaths in real rounds:        {len(md)}")
    print(f"  of which world/self-kills:  {len(suicides)} "
          f"(weapons={suicides['weapon'].tolist()})")
    print(f"deaths excluding suicides:    {len(md) - len(suicides)}  "
          f"<- target 13")

    # ---- assists (real rounds) ------------------------------------------
    if "assister_name" in dd.columns:
        ma = dd[dd["assister_name"] == TARGET].copy()
        ma["rnd"] = ma["tick"].apply(lambda t: round_of(t, bounds))
        pre_a = ma[ma["rnd"].isna()]
        ma = ma[ma["rnd"].notna()]
        print(f"\nassists in real rounds:       {len(ma)}  <- target 7")
        print(f"  (dropped pre-match assists: {len(pre_a)})")

    # ---- kills (sanity, should stay 17) ---------------------------------
    mk = dd[(dd["attacker_name"] == TARGET)
            & (dd["attacker_name"] != dd["user_name"])].copy()
    mk["rnd"] = mk["tick"].apply(lambda t: round_of(t, bounds))
    mk = mk[mk["rnd"].notna()]
    print(f"\nkills in real rounds:         {len(mk)}  <- target 17")


if __name__ == "__main__":
    main(sys.argv[1])
