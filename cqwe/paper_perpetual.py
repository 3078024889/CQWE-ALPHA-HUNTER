"""Conservative linear-USDT perpetual paper-order risk gate.

Research-only math. No exchange client, credentials, network calls, or order endpoint.
Liquidation is a simplified isolated-margin estimate, not an exchange-calculated price.
"""
from __future__ import annotations

import math
from typing import Any

MAX_LEVERAGE = 10.0
BPS = 10_000.0


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def plan_linear_usdt_order(
    *,
    symbol: str,
    side: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
    equity_usdt: float,
    leverage: float = 10.0,
    risk_fraction: float = 0.005,
    fee_bps_each_side: float = 5.0,
    slippage_bps_each_side: float = 2.0,
    min_net_rr: float = 1.5,
    maintenance_margin_rate: float = 0.005,
) -> dict[str, Any]:
    """Return an auditable paper-only plan or a fail-closed rejection.

    Inputs are reference prices for a linear USDT-margined contract. Position size is
    first bounded by equity risk at the stop, then by equity * leverage. Fees and
    adverse slippage are included on entry and exit. No order is submitted.
    """
    if not isinstance(symbol, str) or not symbol or symbol != symbol.upper() or not symbol.endswith("USDT"):
        raise ValueError("symbol must be an uppercase USDT contract, e.g. BTCUSDT")
    side = str(side).upper()
    if side not in {"LONG", "SHORT"}:
        raise ValueError("side must be LONG or SHORT")

    entry = _number(entry_price, "entry_price")
    stop = _number(stop_price, "stop_price")
    target = _number(target_price, "target_price")
    equity = _number(equity_usdt, "equity_usdt")
    lev = _number(leverage, "leverage")
    risk_frac = _number(risk_fraction, "risk_fraction")
    fee_bps = _number(fee_bps_each_side, "fee_bps_each_side")
    slip_bps = _number(slippage_bps_each_side, "slippage_bps_each_side")
    min_rr = _number(min_net_rr, "min_net_rr")
    mmr = _number(maintenance_margin_rate, "maintenance_margin_rate")

    if min(entry, stop, target, equity) <= 0:
        raise ValueError("prices and equity must be positive")
    if not 1.0 <= lev <= MAX_LEVERAGE:
        raise ValueError(f"leverage must be between 1x and {MAX_LEVERAGE:g}x")
    if not 0 < risk_frac <= 0.02:
        raise ValueError("risk_fraction must be in (0, 0.02]")
    if fee_bps < 0 or not 0 <= slip_bps < BPS:
        raise ValueError("fee must be >= 0 and slippage must be in [0, 10000) bps")
    if min_rr <= 0 or not 0 <= mmr < 1.0 / lev:
        raise ValueError("invalid RR or maintenance margin rate")

    if side == "LONG" and not stop < entry < target:
        raise ValueError("LONG requires stop < entry < target")
    if side == "SHORT" and not target < entry < stop:
        raise ValueError("SHORT requires target < entry < stop")

    slip = slip_bps / BPS
    fee_rate = fee_bps / BPS
    # Adverse execution assumptions: buy entries higher, sell entries lower.
    entry_fill = entry * (1 + slip if side == "LONG" else 1 - slip)
    stop_fill = stop * (1 - slip if side == "LONG" else 1 + slip)
    target_fill = target * (1 - slip if side == "LONG" else 1 + slip)

    # Simplified isolated linear contract estimate; excludes tier changes, funding,
    # fee reserves, extra margin and exchange-specific liquidation rules.
    liquidation = entry_fill * (
        1 - 1 / lev + mmr if side == "LONG" else 1 + 1 / lev - mmr
    )
    stop_before_liquidation = stop_fill > liquidation if side == "LONG" else stop_fill < liquidation
    if not stop_before_liquidation:
        return {
            "status": "REJECTED_STOP_AT_OR_BEYOND_ESTIMATED_LIQUIDATION",
            "reason": "The modeled stop is not safely before the simplified liquidation estimate.",
            "symbol": symbol,
            "side": side,
            "leverage": lev,
            "entry_fill_estimate": round(entry_fill, 10),
            "stop_fill_estimate": round(stop_fill, 10),
            "liquidation_price_estimate": round(liquidation, 10),
            "liquidation_estimate_kind": "simplified_isolated_linear_not_exchange_exact",
            "paper_only": True,
            "real_orders": False,
        }

    entry_fee_per_unit = entry_fill * fee_rate
    stop_loss_per_unit = (
        entry_fill - stop_fill if side == "LONG" else stop_fill - entry_fill
    ) + entry_fee_per_unit + stop_fill * fee_rate
    target_pnl_per_unit = (
        target_fill - entry_fill if side == "LONG" else entry_fill - target_fill
    ) - entry_fee_per_unit - target_fill * fee_rate

    if stop_loss_per_unit <= 0:
        raise ValueError("computed stop risk must be positive")
    if target_pnl_per_unit <= 0:
        return {
            "status": "REJECTED_TARGET_NONPOSITIVE_AFTER_COSTS",
            "reason": "Target profit is not positive after modeled fees and slippage.",
            "symbol": symbol,
            "side": side,
            "leverage": lev,
            "paper_only": True,
            "real_orders": False,
        }

    risk_budget = equity * risk_frac
    qty_by_risk = risk_budget / stop_loss_per_unit
    max_notional = equity * lev
    qty_by_leverage = max_notional / entry_fill
    qty = min(qty_by_risk, qty_by_leverage)
    if not math.isfinite(qty) or qty <= 0:
        raise ValueError("computed quantity is invalid")

    notional = qty * entry_fill
    initial_margin = notional / lev
    entry_fee = notional * fee_rate
    stop_exit_fee = qty * stop_fill * fee_rate
    target_exit_fee = qty * target_fill * fee_rate
    stop_net_pnl = qty * (
        stop_fill - entry_fill if side == "LONG" else entry_fill - stop_fill
    ) - entry_fee - stop_exit_fee
    target_net_pnl = qty * (
        target_fill - entry_fill if side == "LONG" else entry_fill - target_fill
    ) - entry_fee - target_exit_fee
    actual_risk = -stop_net_pnl
    net_rr = target_net_pnl / actual_risk if actual_risk > 0 else 0.0

    common = {
        "symbol": symbol,
        "side": side,
        "leverage": lev,
        "entry_reference": entry,
        "entry_fill_estimate": round(entry_fill, 10),
        "stop_reference": stop,
        "stop_fill_estimate": round(stop_fill, 10),
        "target_reference": target,
        "target_fill_estimate": round(target_fill, 10),
        "quantity": round(qty, 10),
        "notional_usdt": round(notional, 8),
        "initial_margin_usdt": round(initial_margin, 8),
        "equity_usdt": round(equity, 8),
        "risk_budget_usdt": round(risk_budget, 8),
        "modeled_stop_loss_usdt": round(actual_risk, 8),
        "modeled_target_profit_usdt": round(target_net_pnl, 8),
        "net_rr": round(net_rr, 6),
        "entry_fee_estimate_usdt": round(entry_fee, 8),
        "liquidation_price_estimate": round(liquidation, 10),
        "liquidation_estimate_kind": "simplified_isolated_linear_not_exchange_exact",
        "paper_only": True,
        "real_orders": False,
    }
    if net_rr < min_rr:
        return {
            **common,
            "status": "REJECTED_NET_RR_BELOW_MINIMUM",
            "reason": f"Net RR {net_rr:.4f} is below required {min_rr:.4f}.",
            "minimum_net_rr": min_rr,
        }
    return {
        **common,
        "status": "APPROVED_PAPER_ONLY",
        "reason": "Risk, costs, direction, notional and simplified liquidation gates passed.",
        "minimum_net_rr": min_rr,
    }
