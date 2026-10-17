"""Copernican V32 isolated-margin paper ledger, schema V2.

Research-only. Public data and close-only indicative fills. No authenticated
exchange client, no private endpoints, and no real-order execution.

Accounting contract:
- cash is free cash after locked margin, entry costs, and funding settlements;
- position margin is included in equity but excluded from free cash;
- notional exposure is independent from margin and equals quantity * entry;
- all costs are explicit and charged exactly once;
- liquidation is a simplified estimate, never an exchange liquidation price.
"""
from __future__ import annotations
import copy
import datetime as dt
import json
import math
import time
from pathlib import Path
from typing import Any

SCHEMA = "V32_PAPER_MARGIN_V2"
INITIAL_EQUITY = 10.0
DEFAULT_LEVERAGE = 10
DEFAULT_MMR = 0.005  # illustrative 0.5%; not a verified Bybit risk-tier value
FEE_BPS_EACH_SIDE = 5.0
SLIPPAGE_BPS_EACH_SIDE = 2.0
NOTIONAL_FRACTION = 0.10  # position notional / equity; NOT margin fraction
MAX_POSITIONS = 2
MAX_MARGIN_FRACTION = 0.20
MAX_STOP_RISK_FRACTION = 0.025


def _finite(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"INVALID_{name.upper()}")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"INVALID_{name.upper()}")
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"INVALID_{name.upper()}")
    return result


def _epoch_ms(value: Any) -> int | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return int(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return int(parsed.timestamp() * 1000)
    except (ValueError, OverflowError):
        return None


def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _new_state() -> dict[str, Any]:
    return {
        "version": SCHEMA,
        "initial_equity": INITIAL_EQUITY,
        "cash": INITIAL_EQUITY,
        "positions": {},
        "trades": [],
        "equity_history": [],
        "strategy_events": [],
        "roll_counts": {},
        "roll_policies": {},
        "migrations": [],
        "margin_mode": "ISOLATED",
        "default_leverage": DEFAULT_LEVERAGE,
        "maintenance_margin_rate": DEFAULT_MMR,
        "fee_bps_each_side": FEE_BPS_EACH_SIDE,
        "slippage_bps_each_side": SLIPPAGE_BPS_EACH_SIDE,
        "real_orders": 0,
        "execution_model": "CLOSED_5M_REFERENCE_PAPER_ONLY",
    }


def migrate_state(state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Migrate known legacy full-notional collateral to an explicit 10x paper assumption.

    For positions whose old schema had neither margin nor leverage, margin is
    set to notional / 10 and the freed collateral is returned to cash. This
    preserves pre-migration equity at the same mark. The migration is explicitly
    labeled as an assumption, not historical evidence of actual leverage.
    A partially populated margin schema is rejected instead of guessed.
    """
    if not isinstance(state, dict):
        raise ValueError("PAPER_STATE_MUST_BE_OBJECT")
    result = copy.deepcopy(state)
    positions = result.get("positions", {})
    if not isinstance(positions, dict):
        raise ValueError("PAPER_POSITIONS_MUST_BE_OBJECT")
    version = result.get("version")
    if version == SCHEMA:
        for symbol, pos in positions.items():
            if not isinstance(pos, dict):
                raise ValueError(f"INVALID_POSITION:{symbol}")
            if "margin" not in pos or "leverage" not in pos:
                raise ValueError(f"V2_POSITION_FIELDS_MISSING:{symbol}")
        return result, False

    cash_before = _finite(result.get("cash", INITIAL_EQUITY), "cash")
    migrated_notional = 0.0
    migrated_margin = 0.0
    migrated_symbols: list[str] = []
    for symbol, pos in positions.items():
        if not isinstance(pos, dict):
            raise ValueError(f"INVALID_POSITION:{symbol}")
        has_margin = "margin" in pos and pos.get("margin") is not None
        has_leverage = "leverage" in pos and pos.get("leverage") is not None
        if has_margin != has_leverage:
            raise ValueError(f"PARTIAL_MARGIN_SCHEMA_REFUSE_GUESS:{symbol}")
        if has_margin and has_leverage:
            raise ValueError(f"LEGACY_VERSION_WITH_MARGIN_FIELDS_REFUSE_AMBIGUOUS_MIGRATION:{symbol}")

        notional = _finite(pos.get("notional"), f"{symbol}_notional", positive=True)
        entry = _finite(pos.get("entry"), f"{symbol}_entry", positive=True)
        side = str(pos.get("side", "")).upper()
        if side not in ("LONG", "SHORT"):
            raise ValueError(f"INVALID_POSITION_SIDE:{symbol}")
        leverage = DEFAULT_LEVERAGE
        margin = notional / leverage
        # Legacy V1 debited the entire notional plus fee+slippage from cash.
        # Release the excess collateral to preserve equity without double-charging.
        cash_before += notional - margin
        migrated_notional += notional
        migrated_margin += margin
        migrated_symbols.append(symbol)
        opened_ms = _epoch_ms(pos.get("opened_at", pos.get("opened_utc")))
        pos.update({
            "margin": round(margin, 12),
            "leverage": leverage,
            "quantity": notional / entry,
            "margin_mode": "ISOLATED",
            "maintenance_margin_rate": _finite(result.get("maintenance_margin_rate", DEFAULT_MMR), "mmr", positive=True),
            "entry_fee_usdt": notional * FEE_BPS_EACH_SIDE / 10_000.0,
            "entry_slippage_usdt": notional * SLIPPAGE_BPS_EACH_SIDE / 10_000.0,
            "legacy_entry_cost_embedded_in_cash": True,
            "funding_paid_usdt": 0.0,
            "last_funding_timestamp_ms": 0,
            "funding_history_gap_possible": opened_ms is None,
            "opened_at_ms": opened_ms if opened_ms is not None else int(time.time() * 1000),
            "leverage_source": "MIGRATION_ASSUMPTION_10X_NOT_HISTORICAL_FACT",
        })
    result["cash"] = round(cash_before, 12)
    result.setdefault("initial_equity", INITIAL_EQUITY)
    result.setdefault("trades", [])
    result.setdefault("equity_history", [])
    result.setdefault("migrations", [])
    result["margin_mode"] = "ISOLATED"
    result["default_leverage"] = DEFAULT_LEVERAGE
    result["maintenance_margin_rate"] = _finite(result.get("maintenance_margin_rate", DEFAULT_MMR), "mmr", positive=True)
    result["fee_bps_each_side"] = _finite(result.get("fee_bps_each_side", FEE_BPS_EACH_SIDE), "fee_bps")
    result["slippage_bps_each_side"] = _finite(result.get("slippage_bps_each_side", SLIPPAGE_BPS_EACH_SIDE), "slippage_bps")
    result["version"] = SCHEMA
    result["real_orders"] = 0
    result["execution_model"] = "CLOSED_5M_REFERENCE_PAPER_ONLY"
    result["migrations"].append({
        "time_utc": _now_utc(),
        "from_version": version or "LEGACY_UNVERSIONED",
        "to_version": SCHEMA,
        "policy": "LEGACY_NOTIONAL_RECLASSIFIED_AS_10X_ISOLATED_PAPER_ASSUMPTION",
        "migrated_positions": migrated_symbols,
        "legacy_notional_usdt": round(migrated_notional, 12),
        "assumed_initial_margin_usdt": round(migrated_margin, 12),
        "cash_before_usdt": round(_finite(state.get("cash", INITIAL_EQUITY), "cash"), 12),
        "cash_after_usdt": round(cash_before, 12),
        "equity_preservation_method": "cash += legacy_notional - assumed_initial_margin; entry costs remain embedded in legacy cash",
        "real_orders": 0,
    })
    return result, True


def _atomic_write(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{__import__('os').getpid()}")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.flush()
        __import__('os').fsync(f.fileno())
    tmp.replace(path)


def load(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return _new_state()
    raw = json.loads(p.read_text(encoding="utf-8-sig"))
    migrated, changed = migrate_state(raw)
    if changed:
        _atomic_write(p, migrated)
    return migrated


def _direction(side: str) -> float:
    normalized = str(side).upper()
    if normalized == "LONG":
        return 1.0
    if normalized == "SHORT":
        return -1.0
    raise ValueError("INVALID_POSITION_SIDE")


def _pnl(pos: dict[str, Any], price: float) -> float:
    entry = _finite(pos.get("entry"), "entry", positive=True)
    notional = _finite(pos.get("notional"), "notional", positive=True)
    mark = _finite(price, "mark", positive=True)
    return notional * ((mark / entry) - 1.0) * _direction(str(pos.get("side", "")))


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)[:240]


def _record_strategy_event(state: dict[str, Any], generated: str, event: str, symbol: str, **details: Any) -> None:
    rows = state.setdefault("strategy_events", [])
    if not isinstance(rows, list):
        rows = state["strategy_events"] = []
    safe_details = _json_safe(details)
    rows.append({"time": generated, "event": event, "symbol": symbol, **safe_details, "real_orders": 0})
    state["strategy_events"] = rows[-2000:]


def _explicit_roll_policy(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or value.get("enabled") is not True:
        return None
    max_rolls = value.get("max_rolls")
    if isinstance(max_rolls, bool) or not isinstance(max_rolls, int) or not 1 <= max_rolls <= 10:
        return None
    return {"enabled": True, "max_rolls": max_rolls}


def liquidation_price_estimate(position: dict[str, Any]) -> float | None:
    """Simplified isolated-margin estimate, not an exchange liquidation price."""
    side = str(position.get("side", "")).upper()
    entry = position.get("entry")
    leverage = position.get("leverage")
    mmr = position.get("maintenance_margin_rate")
    try:
        entry = _finite(entry, "entry", positive=True)
        leverage = _finite(leverage, "leverage", positive=True)
        mmr = _finite(mmr, "mmr", positive=True)
    except ValueError:
        return None
    if side not in ("LONG", "SHORT") or not leverage.is_integer() or not 1 <= leverage <= 10 or not 0 < mmr < 0.5:
        return None
    price = entry * (1.0 - 1.0 / leverage + mmr) if side == "LONG" else entry * (1.0 + 1.0 / leverage - mmr)
    return round(price, 10) if price > 0 and math.isfinite(price) else None


def _mark_for(symbol: str, pos: dict[str, Any], prices: dict[str, Any]) -> float:
    candidate = prices.get(symbol, pos.get("last_mark", pos.get("entry")))
    if isinstance(candidate, dict):
        candidate = candidate.get("mark_price", candidate.get("last_price"))
    if candidate is None:
        candidate = pos.get("last_mark", pos.get("entry"))
    return _finite(candidate, f"{symbol}_mark", positive=True)


def account_snapshot(state: dict[str, Any], prices: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return dashboard metrics without mutating the supplied persistent state."""
    prices = prices or {}
    raw_positions = state.get("positions", {}) if isinstance(state.get("positions"), dict) else {}
    enriched: dict[str, Any] = {}
    missing: list[str] = []
    used_margin = notional_total = current_notional_total = unrealized = close_costs = funding_total = 0.0
    for symbol, original in raw_positions.items():
        if not isinstance(original, dict):
            missing.append(str(symbol)); continue
        pos = copy.deepcopy(original)
        try:
            entry = _finite(pos.get("entry"), f"{symbol}_entry", positive=True)
            notional = _finite(pos.get("notional"), f"{symbol}_notional", positive=True)
            side = str(pos.get("side", "")).upper()
            if side not in ("LONG", "SHORT"):
                raise ValueError("INVALID_SIDE")
            mark = _mark_for(str(symbol), pos, prices)
        except ValueError:
            pos.update({"margin_metrics_status": "INVALID_POSITION_FIELDS", "unrealized_pnl_gross_usdt": None, "liquidation_price_estimate": None})
            enriched[str(symbol)] = pos; missing.append(str(symbol)); continue
        leverage = pos.get("leverage")
        margin = pos.get("margin")
        mmr = pos.get("maintenance_margin_rate")
        if leverage is None or margin is None or mmr is None:
            pos.update({"last_mark": mark, "margin_metrics_status": "MISSING_MARGIN_LEVERAGE_OR_MMR", "unrealized_pnl_gross_usdt": None, "liquidation_price_estimate": None})
            enriched[str(symbol)] = pos; missing.append(str(symbol)); continue
        try:
            leverage = _finite(leverage, f"{symbol}_leverage", positive=True)
            margin = _finite(margin, f"{symbol}_margin", positive=True)
            mmr = _finite(mmr, f"{symbol}_mmr", positive=True)
            if not leverage.is_integer() or not 1 <= leverage <= 10 or not math.isclose(margin * leverage, notional, rel_tol=1e-6, abs_tol=1e-8) or not 0 < mmr < 0.5:
                raise ValueError("INCONSISTENT_MARGIN_MODEL")
            stored_quantity = pos.get("quantity")
            if stored_quantity is not None:
                stored_quantity = _finite(stored_quantity, f"{symbol}_quantity", positive=True)
                if not math.isclose(stored_quantity * entry, notional, rel_tol=1e-6, abs_tol=1e-8):
                    raise ValueError("INCONSISTENT_QUANTITY_NOTIONAL")
        except ValueError:
            pos.update({"last_mark": mark, "margin_metrics_status": "INVALID_MARGIN_MODEL", "unrealized_pnl_gross_usdt": None, "liquidation_price_estimate": None})
            enriched[str(symbol)] = pos; missing.append(str(symbol)); continue
        pnl = _pnl(pos, mark)
        current_notional = notional * mark / entry
        fee = current_notional * _finite(state.get("fee_bps_each_side", FEE_BPS_EACH_SIDE), "fee_bps") / 10_000.0
        slip = current_notional * _finite(state.get("slippage_bps_each_side", SLIPPAGE_BPS_EACH_SIDE), "slippage_bps") / 10_000.0
        funding = _finite(pos.get("funding_paid_usdt", 0.0), f"{symbol}_funding_paid")
        liq = liquidation_price_estimate(pos)
        pos.update({
            "last_mark": mark,
            "quantity": round(notional / entry, 12),
            "margin": round(margin, 12),
            "leverage": leverage,
            "notional_usdt": round(notional, 8),
            "current_notional_usdt": round(current_notional, 8),
            "unrealized_pnl_gross_usdt": round(pnl, 8),
            "estimated_close_fee_usdt": round(fee, 8),
            "estimated_close_slippage_usdt": round(slip, 8),
            "unrealized_pnl_after_est_close_costs_usdt": round(pnl - fee - slip, 8),
            "maintenance_margin_estimate_usdt": round(current_notional * mmr, 8),
            "liquidation_price_estimate": liq,
            "liquidation_model": f"SIMPLIFIED_ISOLATED_MMR_{mmr:.4f}_NOT_EXCHANGE_PRICE",
            "funding_paid_usdt": round(funding, 8),
            "margin_metrics_status": "VALID",
        })
        used_margin += margin; notional_total += notional; current_notional_total += current_notional
        unrealized += pnl; close_costs += fee + slip; funding_total += funding
        enriched[str(symbol)] = pos
    cash = _finite(state.get("cash", 0.0), "cash")
    if state.get("version") != SCHEMA:
        missing.append("__LEDGER_VERSION__")
    equity = cash + used_margin + unrealized if not missing else None
    initial = _finite(state.get("initial_equity", INITIAL_EQUITY), "initial_equity", positive=True)
    trades = state.get("trades", []) if isinstance(state.get("trades"), list) else []
    realized_rows = [t for t in trades if isinstance(t, dict) and t.get("net_pnl") is not None]
    realized = sum(float(t.get("net_pnl", 0.0) or 0.0) for t in realized_rows)
    legacy_trade_rows = sum(1 for t in trades if isinstance(t, dict) and t.get("net_pnl") is None)
    closed_funding = sum(float(t.get("funding_paid_usdt", 0.0) or 0.0) for t in trades if isinstance(t, dict))
    funding_total += closed_funding
    funding_gap_possible = any(bool(p.get("funding_history_gap_possible")) for p in raw_positions.values() if isinstance(p, dict)) or any(bool(t.get("funding_history_gap_possible")) for t in trades if isinstance(t, dict))
    return {
        "schema": SCHEMA,
        "accounting_status": "VERIFIED_MARGIN_LEDGER_V2" if not missing else ("LEGACY_LEDGER_NEEDS_MIGRATION" if "__LEDGER_VERSION__" in missing else "INCOMPLETE_POSITION_FIELDS"),
        "missing_positions": sorted(missing),
        "initial_equity_usdt": round(initial, 8),
        "current_equity_usdt": round(equity, 8) if equity is not None else None,
        "available_cash_usdt": round(cash, 8),
        "used_margin_usdt": round(used_margin, 8),
        "margin_fraction_of_equity": round(used_margin / equity, 8) if equity and equity > 0 else None,
        "initial_notional_usdt": round(notional_total, 8),
        "current_notional_usdt": round(current_notional_total, 8),
        "gross_exposure_to_equity": round(current_notional_total / equity, 8) if equity and equity > 0 else None,
        "unrealized_pnl_gross_usdt": round(unrealized, 8) if not missing else None,
        "estimated_close_costs_usdt": round(close_costs, 8),
        "unrealized_pnl_after_est_close_costs_usdt": round(unrealized - close_costs, 8) if not missing else None,
        "funding_paid_usdt": round(funding_total, 8),
        "realized_net_pnl_usdt": round(realized, 8) if not legacy_trade_rows else None,
        "legacy_trade_rows_without_net_pnl": legacy_trade_rows,
        "funding_history_gap_possible": funding_gap_possible,
        "migration_history_status": (state.get("migration_reconciliation") or {}).get("history_status", "NOT_RECORDED"),
        "migration_history_delta_usdt": (state.get("migration_reconciliation") or {}).get("history_minus_reconstructed_ledger_usdt"),
        "position_count": len(raw_positions),
        "margin_mode": "ISOLATED",
        "maintenance_margin_rate_assumption": state.get("maintenance_margin_rate", DEFAULT_MMR),
        "funding_model": "BYBIT_PUBLIC_FUNDING_HISTORY_SETTLEMENT_EVENTS_WHEN_PRESENT",
        "real_orders": 0,
        "positions": enriched,
    }


def _funding_events(decision: dict[str, Any]) -> list[dict[str, Any]]:
    rows = decision.get("funding_history", [])
    if not isinstance(rows, list):
        return []
    clean = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            ts = int(row.get("ts"))
            rate = _finite(row.get("rate"), "funding_rate")
        except (TypeError, ValueError, OverflowError):
            continue
        if ts > 0:
            clean.append({"ts": ts, "rate": rate})
    return sorted({item["ts"]: item for item in clean}.values(), key=lambda x: x["ts"])


def _apply_funding(pos: dict[str, Any], decision: dict[str, Any], mark: float) -> float:
    """Apply each newly observed historical settlement event once per position.

    Positive funding means longs pay and shorts receive. The position's
    funding_paid_usdt is a signed cost: positive=paid, negative=received.
    """
    events = _funding_events(decision)
    if not events:
        if pos.get("leverage_source") == "MIGRATION_ASSUMPTION_10X_NOT_HISTORICAL_FACT":
            pos["funding_history_gap_possible"] = True
        return 0.0
    last_ts = int(pos.get("last_funding_timestamp_ms", 0) or 0)
    opened_ms = int(pos.get("opened_at_ms", 0) or 0)
    if opened_ms and events and opened_ms < events[0]["ts"]:
        pos["funding_history_gap_possible"] = True
    applied_cost = 0.0
    for event in events:
        if event["ts"] <= last_ts or event["ts"] <= opened_ms:
            continue
        current_notional = float(pos["notional"]) * mark / float(pos["entry"])
        signed_cost = current_notional * event["rate"] * _direction(pos["side"])
        # cost>0 means this account pays; negative means it receives funding.
        pos["funding_paid_usdt"] = round(float(pos.get("funding_paid_usdt", 0.0)) + signed_cost, 12)
        applied_cost += signed_cost
        last_ts = event["ts"]
    pos["last_funding_timestamp_ms"] = last_ts
    return applied_cost


def _validate_open_position(symbol: str, pos: dict[str, Any]) -> None:
    if not isinstance(pos, dict):
        raise ValueError(f"INVALID_POSITION_OBJECT:{symbol}")
    entry = _finite(pos.get("entry"), f"{symbol}_entry", positive=True)
    notional = _finite(pos.get("notional"), f"{symbol}_notional", positive=True)
    margin = _finite(pos.get("margin"), f"{symbol}_margin", positive=True)
    leverage = _finite(pos.get("leverage"), f"{symbol}_leverage", positive=True)
    mmr = _finite(pos.get("maintenance_margin_rate"), f"{symbol}_mmr", positive=True)
    side = str(pos.get("side", "")).upper()
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"INVALID_POSITION_SIDE:{symbol}")
    if pos.get("margin_mode", "ISOLATED") != "ISOLATED":
        raise ValueError(f"UNSUPPORTED_MARGIN_MODE:{symbol}")
    if not leverage.is_integer() or not 1 <= leverage <= 10:
        raise ValueError(f"INVALID_POSITION_LEVERAGE:{symbol}")
    if not math.isclose(margin * leverage, notional, rel_tol=1e-6, abs_tol=1e-8):
        raise ValueError(f"INCONSISTENT_POSITION_MARGIN:{symbol}")
    if not 0 < mmr < 0.5:
        raise ValueError(f"INVALID_POSITION_MMR:{symbol}")
    quantity = pos.get("quantity")
    if quantity is not None:
        quantity = _finite(quantity, f"{symbol}_quantity", positive=True)
        if not math.isclose(quantity * entry, notional, rel_tol=1e-6, abs_tol=1e-8):
            raise ValueError(f"INCONSISTENT_POSITION_QUANTITY:{symbol}")
    _finite(pos.get("stop_invalidation"), f"{symbol}_stop", positive=True)
    _finite(pos.get("dynamic_exit_reference"), f"{symbol}_target", positive=True)


def mark_to_market(state: dict[str, Any], prices: dict[str, Any]) -> float:
    cash = _finite(state.get("cash", 0.0), "cash")
    used_margin = 0.0
    unrealized = 0.0
    for symbol, pos in state.get("positions", {}).items():
        _validate_open_position(str(symbol), pos)
        px = _mark_for(symbol, pos, prices)
        used_margin += _finite(pos["margin"], f"{symbol}_margin", positive=True)
        unrealized += _pnl(pos, px)
    return round(cash + used_margin + unrealized, 12)


def step(state: dict[str, Any], report: dict[str, Any], max_positions: int = MAX_POSITIONS,
         risk_fraction: float = NOTIONAL_FRACTION, fee_bps_each_side: float = FEE_BPS_EACH_SIDE,
         slippage_bps_each_side: float = SLIPPAGE_BPS_EACH_SIDE, leverage: int = DEFAULT_LEVERAGE,
         mmr: float = DEFAULT_MMR, max_margin_fraction: float = MAX_MARGIN_FRACTION,
         max_stop_risk_fraction: float = MAX_STOP_RISK_FRACTION) -> dict[str, Any]:
    """Process one closed 5m paper decision. risk_fraction sizes notional, not margin."""
    migrated, changed = migrate_state(state)
    if changed:
        state.clear(); state.update(migrated)
    if leverage < 1 or leverage > 10 or int(leverage) != leverage:
        raise ValueError("LEVERAGE_MUST_BE_INTEGER_1_TO_10")
    if not 0 < mmr < 0.5 or fee_bps_each_side < 0 or slippage_bps_each_side < 0:
        raise ValueError("INVALID_COST_OR_MMR_CONFIG")
    if not 0 < risk_fraction <= 1 or not 1 <= max_positions <= 4:
        raise ValueError("INVALID_POSITION_SIZING_CONFIG")
    decisions = report.get("decisions", [])
    by_symbol = {d.get("symbol"): d for d in decisions if isinstance(d, dict)}
    prices = {d["symbol"]: d["entry_reference"] for d in decisions if d.get("symbol") and d.get("entry_reference") is not None}
    generated = report.get("generated_utc") or _now_utc()
    generated_ms = _epoch_ms(generated) or int(time.time() * 1000)
    state.setdefault("initial_equity", INITIAL_EQUITY)
    state.setdefault("positions", {})
    state.setdefault("trades", [])
    state.setdefault("equity_history", [])
    if not isinstance(state.get("strategy_events"), list): state["strategy_events"] = []
    if not isinstance(state.get("roll_counts"), dict): state["roll_counts"] = {}
    if not isinstance(state.get("roll_policies"), dict): state["roll_policies"] = {}
    for symbol, position in state["positions"].items():
        _validate_open_position(str(symbol), position)
    state["version"] = SCHEMA
    state["margin_mode"] = "ISOLATED"
    state["default_leverage"] = int(leverage)
    state["maintenance_margin_rate"] = float(mmr)
    state["fee_bps_each_side"] = float(fee_bps_each_side)
    state["slippage_bps_each_side"] = float(slippage_bps_each_side)
    state["real_orders"] = 0

    # First mark positions and settle only newly observed funding-history events.
    for symbol, pos in list(state["positions"].items()):
        d = by_symbol.get(symbol, {})
        mark = _mark_for(symbol, pos, prices)
        pos["last_mark"] = mark
        funding_cost = _apply_funding(pos, d, mark)
        state["cash"] = round(float(state["cash"]) - funding_cost, 12)

    closed: list[str] = []
    rolled_symbols: set[str] = set()
    for symbol, pos in list(state["positions"].items()):
        d = by_symbol.get(symbol)
        if not d:
            continue
        mark = _mark_for(symbol, pos, prices)
        side = pos["side"]
        # Track favorable extremes for explicitly configured trailing stops.
        high_water = max(_finite(pos.get("high_water_mark", pos["entry"]), "high_water", positive=True), mark)
        low_water = min(_finite(pos.get("low_water_mark", pos["entry"]), "low_water", positive=True), mark)
        pos["high_water_mark"] = high_water
        pos["low_water_mark"] = low_water

        # A roll is permitted only with an explicit enabled policy, a selected
        # same-direction decision, and remaining roll budget. It is paper-only.
        action = str(d.get("action", "")).upper()
        policy = _explicit_roll_policy(pos.get("roll_policy"))
        roll_count = int(pos.get("roll_count", 0) or 0)
        wants_roll = str(d.get("roll_action", "")).upper() == "ROLL"
        roll_valid = (wants_roll and policy is not None and d.get("portfolio_selected") is True
                      and action == side and roll_count < policy["max_rolls"])
        if wants_roll and not roll_valid:
            _record_strategy_event(state, generated, "ROLL_REJECTED", symbol,
                                   reason="EXPLICIT_POLICY_SELECTION_DIRECTION_OR_BUDGET_REQUIRED",
                                   roll_count=roll_count, real_orders=0)

        # Stop is immutable after entry: fixed and trailing stops may only tighten.
        proposed_stop = d.get("stop_invalidation")
        stop = pos.get("stop_invalidation")
        if proposed_stop is not None:
            try:
                proposed_stop = _finite(proposed_stop, f"{symbol}_stop", positive=True)
                old_stop = stop
                if stop is None:
                    stop = proposed_stop
                else:
                    stop = max(float(stop), proposed_stop) if side == "LONG" else min(float(stop), proposed_stop)
                if old_stop != stop:
                    _record_strategy_event(state, generated, "STOP_TIGHTENED", symbol,
                                           previous_stop=old_stop, stop=stop)
            except ValueError:
                _record_strategy_event(state, generated, "STOP_INPUT_REJECTED", symbol, value=proposed_stop)
        pos["stop_invalidation"] = stop

        # Explicit trailing stop: either a strategy-supplied price or a fraction
        # from the favorable extreme. Never widen an already established trailing stop.
        proposed_trailing = d.get("trailing_stop", d.get("trailing_stop_price"))
        distance_raw = d.get("trailing_stop_distance_fraction", pos.get("trailing_stop_distance_fraction"))
        distance = None
        if distance_raw is not None:
            try:
                distance = _finite(distance_raw, f"{symbol}_trailing_distance", positive=True)
                if not 0 < distance < 0.5:
                    raise ValueError("TRAILING_DISTANCE_OUT_OF_RANGE")
                pos["trailing_stop_distance_fraction"] = distance
            except ValueError:
                _record_strategy_event(state, generated, "TRAILING_STOP_INPUT_REJECTED", symbol,
                                       reason="DISTANCE_MUST_BE_BETWEEN_0_AND_0_5", value=distance_raw)
                distance = None
        candidate_trailing = None
        if proposed_trailing is not None:
            try:
                candidate_trailing = _finite(proposed_trailing, f"{symbol}_trailing_stop", positive=True)
            except ValueError:
                _record_strategy_event(state, generated, "TRAILING_STOP_INPUT_REJECTED", symbol, value=proposed_trailing)
        favorable_excursion = high_water > float(pos["entry"]) if side == "LONG" else low_water < float(pos["entry"])
        if distance is not None and favorable_excursion:
            calculated = high_water * (1.0 - distance) if side == "LONG" else low_water * (1.0 + distance)
            candidate_trailing = calculated if candidate_trailing is None else (max(candidate_trailing, calculated) if side == "LONG" else min(candidate_trailing, calculated))
        trailing = pos.get("trailing_stop")
        if candidate_trailing is not None:
            previous_trailing = trailing
            trailing = candidate_trailing if trailing is None else (max(float(trailing), candidate_trailing) if side == "LONG" else min(float(trailing), candidate_trailing))
            if previous_trailing != trailing:
                _record_strategy_event(state, generated, "TRAILING_STOP_TIGHTENED", symbol,
                                       previous_trailing_stop=previous_trailing, trailing_stop=trailing,
                                       trailing_stop_distance_fraction=distance)
        pos["trailing_stop"] = trailing

        # Target may migrate only in the profitable direction.
        proposed_target = d.get("dynamic_exit_reference")
        target = pos.get("dynamic_exit_reference")
        if proposed_target is not None:
            try:
                proposed_target = _finite(proposed_target, f"{symbol}_target", positive=True)
                if target is None:
                    target = proposed_target
                elif side == "LONG":
                    target = max(float(target), proposed_target)
                else:
                    target = min(float(target), proposed_target)
            except ValueError:
                _record_strategy_event(state, generated, "TARGET_INPUT_REJECTED", symbol, value=proposed_target)
        pos["dynamic_exit_reference"] = target
        effective_stop = stop
        if trailing is not None:
            effective_stop = float(trailing) if effective_stop is None else (max(float(effective_stop), float(trailing)) if side == "LONG" else min(float(effective_stop), float(trailing)))
        liq = liquidation_price_estimate(pos)
        hit_liq = liq is not None and ((side == "LONG" and mark <= liq) or (side == "SHORT" and mark >= liq))
        hit_stop = effective_stop is not None and ((side == "LONG" and mark <= float(effective_stop)) or (side == "SHORT" and mark >= float(effective_stop)))
        hit_trailing = trailing is not None and hit_stop and (stop is None or (side == "LONG" and float(trailing) >= float(stop)) or (side == "SHORT" and float(trailing) <= float(stop)))
        hit_target = target is not None and ((side == "LONG" and mark >= float(target)) or (side == "SHORT" and mark <= float(target)))
        # Close-only bars cannot establish intrabar event ordering. If mark is beyond
        # the simplified liquidation threshold, choose the conservative liquidation path.
        if hit_liq:
            reason = "SIMULATED_LIQUIDATION_ESTIMATE"
            exit_price = liq
        elif hit_stop:
            reason = "TRAILING_STOP" if hit_trailing else "STOP_INVALIDATION"
            exit_price = mark
        elif hit_target:
            reason = "DYNAMIC_EXIT"
            exit_price = mark
        elif roll_valid:
            reason = "STRATEGY_ROLL"
            exit_price = mark
        else:
            continue
        gross = _pnl(pos, float(exit_price))
        exit_notional = float(pos["notional"]) * float(exit_price) / float(pos["entry"])
        exit_fee = exit_notional * fee_bps_each_side / 10_000.0
        exit_slippage = exit_notional * slippage_bps_each_side / 10_000.0
        margin = float(pos["margin"])
        state["cash"] = round(float(state["cash"]) + margin + gross - exit_fee - exit_slippage, 12)
        entry_fee = float(pos.get("entry_fee_usdt", 0.0))
        entry_slippage = float(pos.get("entry_slippage_usdt", 0.0))
        funding_paid = float(pos.get("funding_paid_usdt", 0.0))
        net = gross - entry_fee - entry_slippage - exit_fee - exit_slippage - funding_paid
        state["trades"].append({
            "time": generated, "symbol": symbol, "side": side, "entry": float(pos["entry"]),
            "exit": float(exit_price), "mark_at_exit": mark, "margin": margin,
            "leverage": int(pos["leverage"]), "notional": float(pos["notional"]),
            "pnl": round(gross, 12), "net_pnl": round(net, 12),
            "entry_fee_usdt": entry_fee, "entry_slippage_usdt": entry_slippage,
            "exit_fee_usdt": round(exit_fee, 12), "exit_slippage_usdt": round(exit_slippage, 12),
            "funding_paid_usdt": round(funding_paid, 12),
            "funding_history_gap_possible": bool(pos.get("funding_history_gap_possible")),
            "reason": reason, "execution_model": "CLOSED_5M_REFERENCE_PAPER_ONLY", "real_orders": 0,
        })
        del state["positions"][symbol]
        if reason == "STRATEGY_ROLL":
            state["roll_counts"][symbol] = int(pos.get("roll_count", 0) or 0) + 1
            state["roll_policies"][symbol] = _explicit_roll_policy(pos.get("roll_policy"))
            rolled_symbols.add(symbol)
        else:
            state["roll_counts"].pop(symbol, None)
            state["roll_policies"].pop(symbol, None)
        _record_strategy_event(state, generated, "POSITION_CLOSED", symbol,
                               reason=reason, exit_price=float(exit_price), net_pnl=round(net, 12))
        closed.append(symbol)

    active_sides = {p.get("side") for p in state["positions"].values()}
    selected = [d for d in decisions if d.get("portfolio_selected")]
    for d in selected:
        if len(state["positions"]) >= max_positions:
            break
        symbol = str(d.get("symbol", "")).upper()
        side = str(d.get("action", "")).upper()
        if side not in ("LONG", "SHORT") or d.get("event_veto") or symbol in state["positions"]:
            continue
        if symbol in closed and symbol not in rolled_symbols:
            _record_strategy_event(state, generated, "REENTRY_BLOCKED_AFTER_EXIT", symbol,
                                   reason="NO_SAME_CYCLE_REENTRY_AFTER_STOP_TARGET_OR_LIQUIDATION")
            continue
        if active_sides and side not in active_sides:
            _record_strategy_event(state, generated, "ENTRY_REJECTED", symbol,
                                   reason="OPPOSING_DIRECTION_BASKET_BLOCKED", side=side)
            continue
        try:
            entry = _finite(d.get("entry_reference"), f"{symbol}_entry", positive=True)
            stop = _finite(d.get("stop_invalidation"), f"{symbol}_stop", positive=True)
            target = _finite(d.get("dynamic_exit_reference"), f"{symbol}_target", positive=True)
        except ValueError:
            continue
        if side == "LONG" and not (stop < entry < target):
            continue
        if side == "SHORT" and not (target < entry < stop):
            continue
        equity = mark_to_market(state, prices)
        notional = equity * risk_fraction
        margin = notional / float(leverage)
        risk_usdt = notional * abs(entry - stop) / entry
        if risk_usdt > equity * max_stop_risk_fraction + 1e-12:
            continue
        used_margin = sum(float(p["margin"]) for p in state["positions"].values())
        if used_margin + margin > equity * max_margin_fraction + 1e-12:
            continue
        entry_fee = notional * fee_bps_each_side / 10_000.0
        entry_slippage = notional * slippage_bps_each_side / 10_000.0
        if float(state["cash"]) < margin + entry_fee + entry_slippage:
            continue
        funding = _funding_events(d)
        latest_seen_funding = max((x["ts"] for x in funding), default=0)
        trailing_stop = d.get("trailing_stop", d.get("trailing_stop_price"))
        trailing_distance = d.get("trailing_stop_distance_fraction")
        if trailing_stop is not None:
            try:
                trailing_stop = _finite(trailing_stop, f"{symbol}_trailing_stop", positive=True)
                if (side == "LONG" and trailing_stop >= entry) or (side == "SHORT" and trailing_stop <= entry):
                    continue
            except ValueError:
                continue
        if trailing_distance is not None:
            try:
                trailing_distance = _finite(trailing_distance, f"{symbol}_trailing_distance", positive=True)
                if not 0 < trailing_distance < 0.5:
                    continue
            except ValueError:
                continue
        roll_policy = _explicit_roll_policy(d.get("roll_policy")) or _explicit_roll_policy(state["roll_policies"].get(symbol))
        roll_count = int(state["roll_counts"].get(symbol, 0) or 0)
        state["cash"] = round(float(state["cash"]) - margin - entry_fee - entry_slippage, 12)
        state["positions"][symbol] = {
            "symbol": symbol, "side": side, "entry": entry, "last_mark": entry,
            "quantity": notional / entry, "notional": notional, "margin": margin,
            "leverage": int(leverage), "margin_mode": "ISOLATED",
            "maintenance_margin_rate": float(mmr),
            "stop_invalidation": stop, "dynamic_exit_reference": target,
            "trailing_stop": trailing_stop, "trailing_stop_distance_fraction": trailing_distance,
            "high_water_mark": entry, "low_water_mark": entry,
            "roll_policy": roll_policy, "roll_count": roll_count,
            "opened_at": generated, "opened_at_ms": generated_ms,
            "entry_fee_usdt": entry_fee, "entry_slippage_usdt": entry_slippage,
            "funding_paid_usdt": 0.0, "last_funding_timestamp_ms": latest_seen_funding,
            "funding_history_gap_possible": False,
            "legacy_entry_cost_embedded_in_cash": False,
            "leverage_source": "V32_PAPER_CONFIG",
            "execution_model": "CLOSED_5M_REFERENCE_PAPER_ONLY", "real_orders": 0,
        }
        active_sides.add(side)
        if roll_policy is not None:
            state["roll_policies"][symbol] = roll_policy
        else:
            state["roll_policies"].pop(symbol, None)
        _record_strategy_event(state, generated, "POSITION_OPENED", symbol,
                               side=side, entry=entry, notional_usdt=notional,
                               margin_usdt=margin, leverage=int(leverage), roll_count=roll_count)
    state["trades"] = state.get("trades", [])[-2000:]
    equity = mark_to_market(state, prices)
    state["equity_history"].append({"time": generated, "equity": equity,
                                    "positions": list(state["positions"]), "real_orders": 0})
    state["equity_history"] = state["equity_history"][-2000:]
    snapshot = account_snapshot(state, prices)
    return {
        "closed": closed, "opened": list(state["positions"]), "equity": equity,
        "available_cash": snapshot["available_cash_usdt"], "used_margin": snapshot["used_margin_usdt"],
        "unrealized_pnl": snapshot["unrealized_pnl_gross_usdt"], "real_orders": 0,
        "accounting_status": snapshot["accounting_status"],
    }


def run_loop(state_path="reports/copernican_v32_paper_state.json", report_path="reports/copernican_v32_live.json",
             cycles=1, interval_seconds=300):
    from .copernican_v32 import run_once, save_report
    state = load(state_path)
    results = []
    for i in range(cycles):
        report = run_once()
        save_report(report, report_path)
        result = step(state, report)
        result["cycle"] = i + 1
        results.append(result)
        _atomic_write(Path(state_path), state)
        if i + 1 < cycles:
            time.sleep(interval_seconds)
    return results


def main():
    import argparse
    p = argparse.ArgumentParser(description="Copernican V32 isolated-margin paper loop; public data only")
    p.add_argument("--cycles", type=int, default=1)
    p.add_argument("--interval", type=int, default=300)
    p.add_argument("--state", default="reports/copernican_v32_paper_state.json")
    p.add_argument("--report", default="reports/copernican_v32_live.json")
    a = p.parse_args()
    if a.cycles < 1 or a.cycles > 10000 or a.interval < 30:
        raise SystemExit("invalid loop bounds")
    print(json.dumps(run_loop(a.state, a.report, a.cycles, a.interval), ensure_ascii=False, indent=2))
    print("CQWE_COPERNICAN_V32_PAPER_MARGIN_V2 | PUBLIC_DATA | REAL_ORDERS=0")


if __name__ == "__main__":
    main()
