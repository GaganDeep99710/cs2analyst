"""
skills.py — per-category skill scores (the radar / progression profile).

Turns the verified per-death + scoreboard + duel + trade signals into six
0-100 category scores. These are HEURISTIC (anchored to sensible good/bad
values), NOT cohort-calibrated — that needs a match corpus we don't have yet.
They are honest and directional: they move the right way when you play better,
and they let a player track progress across matches. Documented anchors below.

Categories: Aim, Fragging, Trading, Entry (dry peeks), Utility, Positioning.
Rotation is deliberately absent — a real rotation score needs positional
timing work; we don't ship a number we can't defend.
"""

import core

CATEGORIES = ["Aim", "Fragging", "Trading", "Entry", "Utility", "Positioning"]

# a "strong player" target line for the radar (the GOAL ring)
GOALS = {"Aim": 78, "Fragging": 75, "Trading": 72,
         "Entry": 70, "Utility": 75, "Positioning": 75}


def _s(x: float, lo: float, hi: float) -> int:
    """Anchor a raw metric to 10-95 (lo -> ~10, hi -> ~95), clamped."""
    t = (x - lo) / (hi - lo) if hi > lo else 0.0
    return round(10 + 85 * max(0.0, min(1.0, t)))


def _mean(xs, default=0.5):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else default


def skill_scores(p, target: str) -> dict:
    board = core.scoreboard(p)
    me = board[board["player"].str.lower() == target.lower()]
    if not len(me):
        return {c: 50 for c in CATEGORIES}
    me = me.iloc[0]

    od = core.opening_duel_stats(p)
    odm = od[od["player"].str.lower() == target.lower()]
    odm = odm.iloc[0] if len(odm) else None
    td = core.trade_stats(p)
    tdm = td[td["player"].str.lower() == target.lower()]
    tdm = tdm.iloc[0] if len(tdm) else None
    db = core.death_breakdown(p, target)

    combat = [d for d in db if d["damage_you_did_to_killer"] is not None]
    won_duel = _mean(d["damage_you_did_to_killer"] >= 50 for d in combat)
    unused = _mean((len(d["unused_grenades_at_death"]) > 0) for d in db)
    fair = [d for d in combat if d["man_advantage"] >= 0]
    untraded_fair = _mean((not d["traded_by_teammate"]) for d in fair)
    predictable = _mean(
        (d["killed_through_smoke"] or d["wallbang"]) for d in combat)

    hs = float(me["HS%"])
    adr = float(me["ADR"])
    kd = float(me["K/D"])
    kpr = float(me["KPR"])

    aim = round((_s(hs, 18, 55) + _s(adr, 55, 110)
                 + _s(won_duel * 100, 20, 62)) / 3)
    frag = round((_s(adr, 55, 110) + _s(kd * 100, 60, 165)
                  + _s(kpr * 100, 45, 95)) / 3)
    trade = (round((_s(float(tdm["Traded%"]), 15, 45)
                    + _s(float(tdm["TradeK"]), 1, 6)) / 2)
             if tdm is not None else 50)
    entry = (_s(float(odm["Win%"]), 25, 60)
             if odm is not None and int(odm["Att"]) >= 2 else 50)
    util = _s((1 - unused) * 100, 40, 92)
    pos = _s((1 - 0.7 * untraded_fair - 0.5 * predictable) * 100, 25, 85)

    return {"Aim": aim, "Fragging": frag, "Trading": trade,
            "Entry": entry, "Utility": util, "Positioning": pos}


if __name__ == "__main__":
    import sys
    p = core.load(sys.argv[1])
    print(skill_scores(p, sys.argv[2]))
