"""
open_duels.py — opening-duel analysis.

The first kill of every round is an "opening duel": the killer won it (entry
kill), the victim lost it (entry death). Your win rate on first contact,
split by side, is a coaching signal a scoreboard can't show.

Usage:
    ./.venv/Scripts/python.exe open_duels.py <demo.dem> [target_name]
"""

import sys

import core


def main(demo_path: str, target: str | None) -> None:
    p = core.load(demo_path)
    duels = core.opening_duels(p)
    stats = core.opening_duel_stats(p)

    print("\nOPENING DUEL, ROUND BY ROUND  (watch these to verify)")
    print(f"{'Rd':>3} {'t':>5}  {'winner':>12} {'':2} {'loser':<12} weapon")
    for _, r in duels.iterrows():
        hs = "*" if r["hs"] else " "
        print(f"{r['round']:>3} {r['t_s']:>5}s  "
              f"{r['killer']:>12} ({r['k_side']:>2}) > "
              f"{r['victim']:<12} ({r['v_side']:>2}) {hs}{r['weapon']}")

    print("\nOPENING DUEL RECORD")
    print("  OpenK=entry kills  OpenD=entry deaths  Att=duels taken")
    print(stats.to_string(index=False))

    if target:
        row = stats[stats["player"].str.lower() == target.lower()]
        print("\n" + "=" * 56)
        if len(row):
            r = row.iloc[0]
            print(f"  YOU - {r['player']}: opening duels {r['OpenK']}/"
                  f"{r['Att']}  ({r['Win%']}% win)")
            print(f"    as CT (holding entry):  {r['CT']}  ({r['CT%']}%)")
            print(f"    as T  (taking entry):   {r['T']}  ({r['T%']}%)")
            _coach(r)
        else:
            print(f"  '{target}' not found.")
        print("=" * 56 + "\n")


def _coach(r) -> None:
    """A stand-in for what the LLM will later say, from the numbers."""
    weak = []
    if r["Att"] >= 4 and r["Win%"] < 45:
        weak.append(f"You're losing first contact ({r['Win%']}%).")
    if r["CT"].endswith(tuple(str(x) for x in range(2, 20))) \
            and r["CT%"] < 40 and int(r["CT"].split("/")[1]) >= 3:
        weak.append(f"CT-side openings are the leak ({r['CT%']}%).")
    if int(r["T"].split("/")[1]) >= 3 and r["T%"] < 40:
        weak.append(f"Your T entries aren't landing ({r['T%']}%).")
    print("    note:", " ".join(weak) if weak
          else "First-contact numbers look healthy.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python open_duels.py <demo.dem> [target_name]")
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
