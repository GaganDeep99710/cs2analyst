"""
core.py — the verified round & stats model.

Every rule in here was confirmed by matching FACEIT's own scoreboard for
match d3c95979 (c0ldrsg: ADR 96.2, 17/13/7). Do not "simplify" these back
to the obvious-but-wrong versions:

  * Real rounds are round_freeze_end events AFTER begin_new_match. NOT the
    round_end count (includes a knife round) and NOT total_rounds_played
    (mislabels rounds around bomb explosions).
  * ADR uses the victim's post-hit `health` field to get HP actually removed.
    This auto-handles overkill, prior damage from other attackers, and armor.
    Summing raw dmg_health over-counts by ~20%.
  * Deaths exclude true self-kills (attacker == victim, e.g. `world`), but a
    bomb death (attacker is None) still counts.
  * Flash assists (assistedflash=True) are separate from regular assists.
"""

import bz2
import gzip
from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser


TEAM_SIDE = {2: "T", 3: "CT"}  # CS2 team_num: 2=T, 3=CT
TRADE_WINDOW_S = 5  # a death is "traded" if avenged within this many seconds

_MAX_DECOMPRESSED = 3 * 1024 ** 3  # 3 GB safety cap (decompression bomb guard)

# inventory reports grenades by display name; map to short labels
GRENADES = {
    "Flashbang": "flash", "Smoke Grenade": "smoke",
    "High Explosive Grenade": "HE", "Molotov": "molotov",
    "Incendiary Grenade": "incendiary", "Decoy Grenade": "decoy",
}


def _ensure_uncompressed(demo_path: str) -> Path:
    """Return a path to a raw .dem. FACEIT/Valve demos arrive compressed
    (zstd/gzip/bz2), often with a misleading .dem name — so detect by magic
    bytes, not extension, and decompress once (cached beside the original)."""
    p = Path(demo_path)
    with open(p, "rb") as f:
        head = f.read(4)

    if head[:2] == b"\x1f\x8b":
        opener = lambda: gzip.open(p, "rb")            # noqa: E731
    elif head[:3] == b"BZh":
        opener = lambda: bz2.open(p, "rb")             # noqa: E731
    elif head == b"\x28\xb5\x2f\xfd":
        import zstandard
        opener = lambda: zstandard.ZstdDecompressor(   # noqa: E731
        ).stream_reader(open(p, "rb"))
    else:
        return p  # already a raw demo (PBDEMS2 / HL2DEMO)

    out = p.with_name(p.stem + "_raw.dem")
    if out.exists() and out.stat().st_size > 0:
        return out
    written = 0
    with opener() as src, open(out, "wb") as dst:
        while chunk := src.read(1 << 20):
            written += len(chunk)
            if written > _MAX_DECOMPRESSED:
                dst.close()
                out.unlink(missing_ok=True)
                raise ValueError("demo decompressed too large — refusing")
            dst.write(chunk)
    return out


def load(demo_path: str) -> DemoParser:
    # demoparser2 needs a Windows-style path, not a Git Bash /d/ path.
    # Transparently decompress zstd/gzip/bz2 demos first.
    return DemoParser(str(_ensure_uncompressed(demo_path)))


def tickrate(p: DemoParser) -> int:
    """Infer tickrate from game_time (seconds) vs tick, robust to 64/128."""
    df = p.parse_event("player_death", other=["game_time"])
    df = df.dropna(subset=["game_time"]).sort_values("tick")
    if len(df) < 2:
        return 64
    dt = float(df["tick"].iloc[-1] - df["tick"].iloc[0])
    dg = float(df["game_time"].iloc[-1] - df["game_time"].iloc[0])
    return round(dt / dg) if dg > 0 else 64


def real_round_bounds(p: DemoParser) -> list[tuple[int, int]]:
    """(start_tick, end_tick) per real round. end is exclusive."""
    match_start = int(p.parse_event("begin_new_match")["tick"].min())
    freeze_ends = sorted(p.parse_event("round_freeze_end")["tick"].tolist())
    starts = [t for t in freeze_ends if t > match_start]
    return [
        (s, starts[i + 1] if i + 1 < len(starts) else 10**12)
        for i, s in enumerate(starts)
    ]


def round_of(tick: int, bounds: list[tuple[int, int]]) -> int | None:
    """Which real round a tick falls in, or None if pre-match (warmup/knife)."""
    for i, (s, e) in enumerate(bounds):
        if s <= tick < e:
            return i
    return None


def scoreboard(p: DemoParser) -> pd.DataFrame:
    bounds = real_round_bounds(p)
    n = len(bounds)

    deaths = p.parse_event("player_death")
    deaths = deaths.copy()
    deaths["rnd"] = deaths["tick"].map(lambda t: round_of(t, bounds))
    deaths = deaths[deaths["rnd"].notna()]

    # kills: attacker credited, exclude self-kills
    kills = deaths[
        deaths["attacker_name"].notna()
        & (deaths["attacker_name"] != deaths["user_name"])
    ]
    k = kills.groupby("attacker_name").size()
    hs = kills[kills["headshot"] == True].groupby(  # noqa: E712
        "attacker_name").size()

    # deaths: exclude true self-kills; bomb deaths (attacker None) still count
    real_deaths = deaths[deaths["attacker_name"] != deaths["user_name"]]
    d = real_deaths.groupby("user_name").size()

    # assists: separate flash assists from regular
    reg = deaths[
        (deaths["assister_name"].notna())
        & (deaths["assistedflash"] != True)  # noqa: E712
    ]
    a = reg.groupby("assister_name").size()
    fa = deaths[deaths["assistedflash"] == True].groupby(  # noqa: E712
        "assister_name").size()

    dmg = _damage_by_player(p, bounds)

    names = sorted(
        name
        for name in (set(k.index) | set(d.index) | set(a.index) | set(dmg))
        if isinstance(name, str) and name
    )
    rows = []
    for name in names:
        kk, dd_ = int(k.get(name, 0)), int(d.get(name, 0))
        dm = dmg.get(name, 0.0)
        hh = int(hs.get(name, 0))
        rows.append({
            "player": name,
            "K": kk,
            "D": dd_,
            "A": int(a.get(name, 0)),
            "FA": int(fa.get(name, 0)),
            "K-D": kk - dd_,
            "K/D": round(kk / dd_, 2) if dd_ else float(kk),
            "ADR": round(dm / n, 1) if n else 0.0,
            "HS%": round(100 * hh / kk) if kk else 0,
            "KPR": round(kk / n, 2) if n else 0.0,
        })
    return pd.DataFrame(rows).sort_values("K", ascending=False)


def opening_duels(p: DemoParser) -> pd.DataFrame:
    """One row per real round: the first kill (the opening duel)."""
    bounds = real_round_bounds(p)
    tr = tickrate(p)
    deaths = p.parse_event(
        "player_death", player=["team_num", "X", "Y"]
    ).copy()
    deaths["rnd"] = deaths["tick"].map(lambda t: round_of(t, bounds))
    deaths = deaths[
        deaths["rnd"].notna()
        & deaths["attacker_name"].notna()
        & (deaths["attacker_name"] != deaths["user_name"])
    ]
    first = (
        deaths.sort_values("tick").groupby("rnd", as_index=False).first()
    )

    rows = []
    for _, r in first.iterrows():
        rnd = int(r["rnd"])
        start = bounds[rnd][0]
        rows.append({
            "round": rnd + 1,
            "t_s": round((r["tick"] - start) / tr, 1),
            "killer": r["attacker_name"],
            "k_side": TEAM_SIDE.get(int(r["attacker_team_num"]), "?"),
            "victim": r["user_name"],
            "v_side": TEAM_SIDE.get(int(r["user_team_num"]), "?"),
            "weapon": r["weapon"],
            "hs": bool(r["headshot"]),
            "k_x": r.get("attacker_X"), "k_y": r.get("attacker_Y"),
            "v_x": r.get("user_X"), "v_y": r.get("user_Y"),
        })
    return pd.DataFrame(rows)


def opening_duel_stats(p: DemoParser) -> pd.DataFrame:
    """Per-player opening-duel record, with a CT/T split."""
    od = opening_duels(p)
    agg: dict[str, dict] = {}

    def bump(name, side, won):
        d = agg.setdefault(name, {
            "OpenK": 0, "OpenD": 0,
            "CT_w": 0, "CT_l": 0, "T_w": 0, "T_l": 0,
        })
        if won:
            d["OpenK"] += 1
            d[f"{side}_w"] += 1
        else:
            d["OpenD"] += 1
            d[f"{side}_l"] += 1

    for _, r in od.iterrows():
        bump(r["killer"], r["k_side"], won=True)
        bump(r["victim"], r["v_side"], won=False)

    rows = []
    for name, d in agg.items():
        att = d["OpenK"] + d["OpenD"]
        ct_att = d["CT_w"] + d["CT_l"]
        t_att = d["T_w"] + d["T_l"]
        rows.append({
            "player": name,
            "OpenK": d["OpenK"],
            "OpenD": d["OpenD"],
            "Att": att,
            "Win%": round(100 * d["OpenK"] / att) if att else 0,
            "CT": f"{d['CT_w']}/{ct_att}",
            "CT%": round(100 * d["CT_w"] / ct_att) if ct_att else 0,
            "T": f"{d['T_w']}/{t_att}",
            "T%": round(100 * d["T_w"] / t_att) if t_att else 0,
        })
    return (
        pd.DataFrame(rows)
        .sort_values(["Att", "Win%"], ascending=False)
        .reset_index(drop=True)
    )


def trade_events(p: DemoParser) -> pd.DataFrame:
    """Per real kill: was the victim's death traded (avenged) within window?

    V dies to X. Traded if a teammate of V kills X within TRADE_WINDOW_S.
    Also flags the opening death of each round so we can ask "were your
    entry deaths traded?".
    """
    bounds = real_round_bounds(p)
    tr = tickrate(p)
    window = TRADE_WINDOW_S * tr

    d = p.parse_event("player_death", player=["team_num"]).copy()
    d["rnd"] = d["tick"].map(lambda t: round_of(t, bounds))
    d = d[
        d["rnd"].notna()
        & d["attacker_name"].notna()
        & (d["attacker_name"] != d["user_name"])
    ].sort_values("tick").reset_index(drop=True)

    opening_tick = d.groupby("rnd")["tick"].transform("min")
    d["is_opening"] = d["tick"] == opening_tick

    traded, avenger = [], []
    for _, row in d.iterrows():
        killer = row["attacker_name"]
        victim_team = row["user_team_num"]
        # a later kill in the same round where the killer(X) is the victim,
        # by a teammate of the original victim, inside the window
        cand = d[
            (d["rnd"] == row["rnd"])
            & (d["tick"] > row["tick"])
            & (d["tick"] <= row["tick"] + window)
            & (d["user_name"] == killer)
            & (d["attacker_team_num"] == victim_team)
        ]
        if len(cand):
            traded.append(True)
            avenger.append(cand.iloc[0]["attacker_name"])
        else:
            traded.append(False)
            avenger.append(None)
    d["traded"] = traded
    d["avenger"] = avenger
    return d[[
        "rnd", "tick", "user_name", "user_team_num", "attacker_name",
        "is_opening", "traded", "avenger",
    ]]


def trade_stats(p: DemoParser) -> pd.DataFrame:
    """Per-player: deaths traded %, trade kills, and entry-death trade rate."""
    ev = trade_events(p)

    # trade kills: each avenging kill is credited once to the avenger.
    trade_kills: dict[str, int] = {}
    for name in ev["avenger"].dropna():
        trade_kills[name] = trade_kills.get(name, 0) + 1

    names = sorted(set(ev["user_name"]) | set(trade_kills))
    rows = []
    for name in names:
        mine = ev[ev["user_name"] == name]
        deaths = len(mine)
        td = int(mine["traded"].sum())
        entry_deaths = mine[mine["is_opening"]]
        ed = len(entry_deaths)
        ed_traded = int(entry_deaths["traded"].sum())
        rows.append({
            "player": name,
            "Deaths": deaths,
            "Traded": td,
            "Traded%": round(100 * td / deaths) if deaths else 0,
            "TradeK": trade_kills.get(name, 0),
            "EntryD": ed,
            "EntryD_traded": f"{ed_traded}/{ed}",
        })
    return (
        pd.DataFrame(rows)
        .sort_values("Deaths", ascending=False)
        .reset_index(drop=True)
    )


def death_breakdown(p: DemoParser, target: str) -> list[dict]:
    """Every death the target suffered, with the raw signals behind it.

    This is the input to round-by-round coaching: for each death we surface
    what the demo actually recorded — weapon, through-smoke, wallbang, whether
    the killer was flashed (a duel you should have won), whether it was the
    round's opening duel, whether a teammate traded it, range, and timing.
    Bomb and fall deaths are included and labelled.
    """
    bounds = real_round_bounds(p)
    tr = tickrate(p)
    window = TRADE_WINDOW_S * tr

    d = p.parse_event(
        "player_death", player=["team_num", "X", "Y", "Z"]
    ).copy()
    d["rnd"] = d["tick"].map(lambda t: round_of(t, bounds))
    d = d[d["rnd"].notna()].sort_values("tick").reset_index(drop=True)

    combat = d[
        d["attacker_name"].notna() & (d["attacker_name"] != d["user_name"])
    ]
    opening_tick = combat.groupby("rnd")["tick"].min().to_dict()

    def traded(row) -> bool:
        cand = combat[
            (combat["rnd"] == row["rnd"])
            & (combat["tick"] > row["tick"])
            & (combat["tick"] <= row["tick"] + window)
            & (combat["user_name"] == row["attacker_name"])
            & (combat["attacker_team_num"] == row["user_team_num"])
        ]
        return len(cand) > 0

    def flag(row, col) -> bool:
        return col in row and bool(pd.notna(row[col])) and bool(row[col])

    mine = d[d["user_name"].str.lower() == target.lower()].sort_values("tick")
    tname = mine.iloc[0]["user_name"] if len(mine) else target

    # man-advantage: every death in each round, to count who's alive
    all_deaths = d[["rnd", "tick", "user_team_num"]]
    # duel quality: damage the target dealt (to know if you were winning)
    hurt = p.parse_event("player_hurt").copy()
    hurt["rnd"] = hurt["tick"].map(lambda t: round_of(t, bounds))
    my_hurt = hurt[hurt["attacker_name"] == tname]

    # utility: grenades still held ~0.5s before death (inventory is empty AT
    # the death tick because weapons drop), and whether you were flashed.
    inv_lookup: dict[int, list] = {}
    inv_ticks = [int(t) - 32 for t in mine["tick"]]
    if inv_ticks:
        idf = p.parse_ticks(["inventory"], ticks=inv_ticks)
        idf = idf[idf["name"] == tname]
        for _, ir in idf.iterrows():
            inv_lookup[int(ir["tick"])] = ir["inventory"] or []
    blind = p.parse_event("player_blind")
    blind_me = (blind[blind["user_name"] == tname]
                if len(blind) and "user_name" in blind.columns
                else blind.iloc[0:0])

    out = []
    for _, r in mine.iterrows():
        killer = r["attacker_name"]
        weapon = str(r.get("weapon") or "")
        is_bomb = (not isinstance(killer, str)) and weapon.startswith("planted")
        is_suicide = killer == r["user_name"]
        rnd = int(r["rnd"])
        combat_death = isinstance(killer, str) and not is_suicide

        # who was alive when you died (5v5 start assumed)
        team = r["user_team_num"]
        prior = all_deaths[(all_deaths["rnd"] == r["rnd"])
                           & (all_deaths["tick"] < r["tick"])]
        you_side = 5 - int((prior["user_team_num"] == team).sum())
        enemy = 5 - int(((prior["user_team_num"] != team)
                         & prior["user_team_num"].isin([2, 3])).sum())
        # how much you'd hurt your killer before they killed you
        dmg_to_killer = None
        if combat_death:
            dk = my_hurt[(my_hurt["rnd"] == r["rnd"])
                         & (my_hurt["user_name"] == killer)
                         & (my_hurt["tick"] < r["tick"])]
            dmg_to_killer = int(dk["dmg_health"].sum())

        # utility held when you died, and whether you died flashed
        inv = inv_lookup.get(int(r["tick"]) - 32, [])
        unused = [GRENADES[w] for w in inv if w in GRENADES]
        active = blind_me[
            (blind_me["tick"] <= r["tick"])
            & (blind_me["tick"] + blind_me["blind_duration"] * tr >= r["tick"])
        ]
        flashed = bool(len(active) and float(active["blind_duration"].max()) >= 1.0)
        out.append({
            "round": rnd + 1,
            "side": TEAM_SIDE.get(int(r["user_team_num"]), "?"),
            "seconds_into_round": round((r["tick"] - bounds[rnd][0]) / tr, 1),
            "killed_by": ("the bomb exploding" if is_bomb
                          else "fall/world damage" if is_suicide
                          else killer),
            "weapon": None if (is_bomb or is_suicide) else weapon or None,
            "headshot": flag(r, "headshot") if combat_death else False,
            "killed_through_smoke": flag(r, "thrusmoke"),
            "wallbang": flag(r, "penetrated"),
            "no_scope": flag(r, "noscope"),
            "killer_was_blind": flag(r, "attackerblind"),
            "distance_units": (int(r["distance"])
                               if "distance" in r and pd.notna(r["distance"])
                               and combat_death else None),
            "was_round_opening_duel": bool(
                combat_death and r["tick"] == opening_tick.get(rnd)),
            "traded_by_teammate": bool(traded(r)) if combat_death else False,
            "situation_when_you_died": f"{you_side}v{enemy}",
            "man_advantage": you_side - enemy,
            "damage_you_did_to_killer": dmg_to_killer,
            "unused_grenades_at_death": unused,
            "flashed_when_you_died": flashed,
            "x": float(r["user_X"]) if pd.notna(r.get("user_X")) else None,
            "y": float(r["user_Y"]) if pd.notna(r.get("user_Y")) else None,
            "z": float(r["user_Z"]) if pd.notna(r.get("user_Z")) else None,
        })
    return out


def _damage_by_player(
    p: DemoParser, bounds: list[tuple[int, int]]
) -> dict[str, float]:
    """Authoritative HP-removed damage per attacker, capped & team-filtered."""
    hurt = p.parse_event("player_hurt", player=["team_num"]).copy()
    hurt["rnd"] = hurt["tick"].map(lambda t: round_of(t, bounds))
    hurt = hurt[hurt["rnd"].notna()].sort_values("tick")

    has_team = {"attacker_team_num", "user_team_num"}.issubset(hurt.columns)
    prev: dict[tuple, float] = {}
    out: dict[str, float] = {}
    for _, r in hurt.iterrows():
        key = (r["rnd"], r["user_name"])
        removed = max(prev.get(key, 100.0) - float(r["health"]), 0.0)
        prev[key] = float(r["health"])
        atk = r["attacker_name"]
        if not atk or atk == r["user_name"]:
            continue
        if has_team and r["attacker_team_num"] == r["user_team_num"]:
            continue
        out[atk] = out.get(atk, 0.0) + removed
    return out
