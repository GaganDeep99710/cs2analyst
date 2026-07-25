"""
trades.py — trade analysis.

A death is "traded" when a teammate kills the killer within
core.TRADE_WINDOW_S seconds. Pairs with opening duels: it tells you whether
your team picks you back up when you lose a fight, and whether you pick them up.

Usage:
    ./.venv/Scripts/python.exe trades.py <demo.dem> [target_name]
"""

import sys

import core


def main(demo_path: str, target: str | None) -> None:
    p = core.load(demo_path)
    stats = core.trade_stats(p)

    print(f"\nTRADE WINDOW: {core.TRADE_WINDOW_S}s")
    print("  Traded% = your deaths a teammate avenged")
    print("  TradeK  = kills where you avenged a teammate")
    print("  EntryD_traded = of your opening deaths, how many were traded\n")
    print(stats.to_string(index=False))

    if not target:
        return

    ev = core.trade_events(p)
    row = stats[stats["player"].str.lower() == target.lower()]
    print("\n" + "=" * 58)
    if not len(row):
        print(f"  '{target}' not found.")
        print("=" * 58 + "\n")
        return
    r = row.iloc[0]
    print(f"  YOU - {r['player']}")
    print(f"    deaths traded:  {r['Traded']}/{r['Deaths']} "
          f"({r['Traded%']}%)   trade kills you got: {r['TradeK']}")
    print(f"    entry deaths traded: {r['EntryD_traded']}")

    # show the player's own deaths and whether each was traded
    mine = ev[ev["user_name"].str.lower() == target.lower()]
    print("\n    your deaths this match:")
    for _, d in mine.iterrows():
        tag = "OPEN " if d["is_opening"] else "     "
        if d["traded"]:
            print(f"      Rd {int(d['rnd']) + 1:>2} {tag}killed by "
                  f"{d['attacker_name']:<12} -> TRADED by {d['avenger']}")
        else:
            print(f"      Rd {int(d['rnd']) + 1:>2} {tag}killed by "
                  f"{d['attacker_name']:<12} -> not traded")
    print("=" * 58 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python trades.py <demo.dem> [target_name]")
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
