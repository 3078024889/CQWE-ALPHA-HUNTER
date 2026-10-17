"""Independent arithmetic reproduction; never executes third-party bot code."""
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / "reports/polymarket_sources_20261015/realfish_bot.txt"
    body = source.read_bytes()
    text = body.decode("utf-8")
    expected = ["Math.floor(tradeAmountCents / (polyPrice || 1))",
                "Math.floor(tradeAmountCents / (kalshiPrice || 1))"]
    if not all(fragment in text for fragment in expected):
        raise ValueError("Retrieved source no longer matches the formula under review")
    budget_per_leg = Decimal("10")
    yes_price, no_price = Decimal("0.41"), Decimal("0.57")
    yes_shares = (budget_per_leg / yes_price).to_integral_value(rounding=ROUND_FLOOR)
    no_shares = (budget_per_leg / no_price).to_integral_value(rounding=ROUND_FLOOR)
    cost = yes_shares * yes_price + no_shares * no_price
    result = {
        "mode": "INDEPENDENT_ARITHMETIC_COUNTEREXAMPLE",
        "upstream_code_executed": False, "real_orders": 0,
        "source_url": "https://github.com/realfishsam/prediction-market-arbitrage-bot/blob/main/src/bot.js",
        "source_sha256": hashlib.sha256(body).hexdigest(),
        "formula_present_in_saved_source": True,
        "scenario": {"budget_per_leg": str(budget_per_leg), "yes_price": str(yes_price),
                     "no_price": str(no_price), "yes_shares": str(yes_shares),
                     "no_shares": str(no_shares), "combined_actual_cost": str(cost),
                     "yes_wins_pnl_before_costs": str(yes_shares - cost),
                     "no_wins_pnl_before_costs": str(no_shares - cost)},
        "assumptions": ["Same binary event and identical resolution rules", "Full fills at stated prices",
                        "No fees, slippage, voiding or settlement failure"],
        "conclusion": "Equal currency amounts do not produce an equal-share hedge. A positive quoted pair edge alone is insufficient.",
    }
    assert yes_shares == 24 and no_shares == 17
    assert cost == Decimal("19.53") and no_shares - cost == Decimal("-2.53")
    target = ROOT / "reports/polymarket_unequal_legs_20261015.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["scenario"]))


if __name__ == "__main__":
    main()
