"""
replay.py — reconstruct a 2D top-down mini-replay for each death.

From the same parsed demo, pulls every player's position for the ~4.5s leading
up to each of the target's deaths, and packages a compact per-death payload the
report renders as an interactive canvas over the map radar. World->radar mapping
uses Valve's own overview calibration (radars/calib.json), extracted from the
game files. No extra parse cost beyond one batched parse_ticks call.
"""

import core

TICKRATE = 64
PRE_S = 4.5            # seconds of lead-up shown
STEP = 6              # sample every Nth tick (~10.7 fps) to keep payloads small
_WANT = ["X", "Y", "health", "team_num"]


def build_replays(p, target: str) -> dict:
    """Return {round_number: replay_payload} for every combat death of target."""
    bounds = core.real_round_bounds(p)
    dd = p.parse_event("player_death")
    vcol = "user_name" if "user_name" in dd.columns else "victim_name"
    mine = dd[dd[vcol].str.lower() == target.lower()]

    # collect the death tick + killer per round, and the union of all ticks
    deaths, all_ticks = {}, set()
    for _, r in mine.iterrows():
        killer = r.get("attacker_name")
        # skip non-combat deaths (bomb/fall/world) — no killer to show
        if killer is None or (isinstance(killer, float) and killer != killer):
            continue
        weapon = str(r.get("weapon") or "")
        if weapon in ("planted_c4", "world", "worldspawn", "trigger_hurt"):
            continue
        dt = int(r["tick"])
        rnd = core.round_of(dt, bounds)
        if rnd is None:
            continue
        start = dt - PRE_S * TICKRATE
        ticks = list(range(int(start), dt + 1, STEP))
        if len(ticks) < 3:
            continue
        deaths[rnd] = {"death_tick": dt, "ticks": ticks, "killer": killer}
        all_ticks.update(ticks)

    if not all_ticks:
        return {}

    df = p.parse_ticks(_WANT, ticks=sorted(all_ticks))
    by_tick = {t: g for t, g in df.groupby("tick")}

    out = {}
    for rnd, d in deaths.items():
        payload = _one(d, by_tick, target)
        if payload:
            out[rnd] = payload
    return out


def _one(d: dict, by_tick: dict, target: str) -> dict | None:
    frames_rows = []
    for t in d["ticks"]:
        g = by_tick.get(t)
        if g is None:
            continue
        frames_rows.append((t, g))
    if len(frames_rows) < 3:
        return None

    # stable roster from the death frame (last), so indices line up per frame
    _, last = frames_rows[-1]
    roster, idx = [], {}
    for i, (_, r) in enumerate(last.iterrows()):
        tm = int(r["team_num"]) if r["team_num"] == r["team_num"] else 0
        roster.append({"n": r["name"], "tm": tm})
        idx[r["name"]] = i

    frames = []
    for _, g in frames_rows:
        pos = [None] * len(roster)
        for _, r in g.iterrows():
            i = idx.get(r["name"])
            if i is None:
                continue
            pos[i] = [int(r["X"]), int(r["Y"]), 1 if r["health"] > 0 else 0]
        # fill any gaps with a dead-offscreen marker so arrays stay aligned
        frames.append([pp if pp else [0, 0, 0] for pp in pos])

    ti = idx.get(target)
    ki = idx.get(d["killer"])
    # zoom bbox around target + killer paths
    pts = []
    for fr in frames:
        for who in (ti, ki):
            if who is not None:
                pts.append((fr[who][0], fr[who][1]))
    xs = [x for x, _ in pts] or [0]
    ys = [y for _, y in pts] or [0]
    pad = 450
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad
    span = max(x1 - x0, y1 - y0, 800)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return {
        "roster": roster, "target_i": ti, "killer_i": ki,
        "bbox": [round(cx - span / 2), round(cy + span / 2), round(span)],
        "f": frames,
    }
