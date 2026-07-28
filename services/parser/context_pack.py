"""
context_pack.py — assemble the structured context the LLM sees (per-death).

Built DETERMINISTICALLY from verified data. The model never touches the demo,
only this: the player's stat line plus every death with the raw signals behind
it (weapon, through-smoke, wallbang, was-it-the-opening-duel, was-it-traded).
The model's job is to explain each death and say how to fix it — never to
compute numbers or invent details the signals don't contain.
"""

import json

import callouts
import core
import skills


def build_pack(demo_path: str, target: str, p=None) -> dict:
    p = p if p is not None else core.load(demo_path)
    header = p.parse_header()
    n = len(core.real_round_bounds(p))

    board = core.scoreboard(p)
    me = board[board["player"].str.lower() == target.lower()]
    if not len(me):
        raise SystemExit(f"'{target}' not in match. Players: "
                         f"{', '.join(board['player'])}")
    me = me.iloc[0]

    map_name = header.get("map_name")
    deaths = core.death_breakdown(p, target)
    for d in deaths:
        d.pop("distance_units", None)  # unit unreliable
        # resolve the callout where the death happened (Valve's own data)
        loc = callouts.resolve(map_name, d.pop("x", None),
                               d.pop("y", None), d.pop("z", None))
        d["location"] = loc

    return {
        "identity": {
            "player": me["player"],
            "map": header.get("map_name"),
            "mode": "FACEIT 5v5 MR12",
            "rounds_played": n,
            "total_deaths": len(deaths),
        },
        "skills": skills.skill_scores(p, target),
        "your_scoreboard": {
            "kills": int(me["K"]), "deaths": int(me["D"]),
            "assists": int(me["A"]),
            "kd_ratio": float(me["K/D"]), "adr": float(me["ADR"]),
            "headshot_pct": int(me["HS%"]),
            "note": "verified equal to FACEIT's own scoreboard",
        },
        "deaths": deaths,
        "signal_glossary": {
            "was_round_opening_duel": "you lost the FIRST fight of the round "
                "— putting your team down a player before the round developed",
            "traded_by_teammate": "true = a teammate killed your killer right "
                "after, so the death was even; false = your team got nothing "
                "for it (you died isolated / too far from support)",
            "killed_through_smoke": "the enemy shot you through a smoke — you "
                "were standing in a spot silhouetted or predictable in/behind "
                "the smoke",
            "wallbang": "you were killed through a wall — you held a common "
                "pre-fire/wallbang spot",
            "killer_was_blind": "the enemy was flashed when they killed you — "
                "a duel you should have won; an aim/crosshair-placement loss",
            "killed_by='the bomb exploding'": "you were alive when the bomb "
                "went off — you failed to defuse, retake in time, or escape",
            "weapon like glock/tec9/fiveseven/deagle/p250": "you died to a "
                "pistol — likely an enemy on a save/eco you should have "
                "played more carefully around",
            "seconds_into_round": "how early you died; a very low number means "
                "you died in the opening seconds",
            "location": "the map callout where you died (Valve's own callout "
                "name) — e.g. Banana, Pit, Apartments, Mid. Use it.",
            "situation_when_you_died": "how many were alive per side, your team "
                "first (e.g. '1v3' = you alone against 3). Critical context.",
            "man_advantage": "your side minus enemies alive. NEGATIVE means your "
                "team was already down players and the round was likely lost — "
                "a death here is usually NOT your mistake; don't scold it. 0 is "
                "a fair fight. POSITIVE means you had the man-advantage and threw "
                "it — those are the most coachable deaths.",
            "damage_you_did_to_killer": "HP you took off your killer before they "
                "killed you. ~0 = you were caught out / lost the aim duel clean "
                "(positioning, crosshair placement, surprised). HIGH (60+) = you "
                "were WINNING and lost the END of the duel (spray control, reload "
                "timing, or unlucky) — a totally different lesson than being "
                "dinked for free.",
            "unused_grenades_at_death": "grenades you were STILL HOLDING when you "
                "died — utility you paid for and never used. Dying with a flash, "
                "smoke or HE in the bag is one of the most common, most fixable "
                "mistakes: that flash could have won the peek, that smoke could "
                "have blocked the angle that killed you. Name the specific nade "
                "and how using it would have changed the death.",
            "flashed_when_you_died": "you were blinded at the moment you died — "
                "you couldn't see your killer. You either peeked into a flash or "
                "held an angle while blind. The fix: don't take or hold fights "
                "while flashed; back off and re-peek when you can see.",
        },
        "coaching_rules": [
            "WEIGHT by situation. Do NOT criticize deaths where man_advantage is "
            "negative — the round was already lost before you died; acknowledge "
            "briefly or note the team lost it earlier, don't blame you. Spend "
            "your real coaching on fair (0) and advantage (positive) deaths.",
            "Use damage_you_did_to_killer to separate positioning/aim mistakes "
            "(low damage — caught out) from won-duel-lost-at-the-end mistakes "
            "(high damage — spray/reload/patience). They need different fixes.",
            "If you died holding unused grenades, that is usually PART of the "
            "mistake — name the nade and how it would have helped (flash to take "
            "the peek, smoke to block the angle, HE to soften). If you died "
            "flashed, that's the mistake — you fought blind.",
            "USE the location callout — name where it happened ('you over-peeked "
            "Banana', 'you got picked in Pit'). Locations are exact game data.",
            "Every death gets a one-line what-happened, the mistake, and a "
            "concrete fix. Ground each strictly in that death's own signals. "
            "If a death was unavoidable (lost man-count), say so honestly.",
        ],
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        sys.exit("usage: python context_pack.py <demo.dem> <target>")
    print(json.dumps(build_pack(sys.argv[1], sys.argv[2]), indent=2))
