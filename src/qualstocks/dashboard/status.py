from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from qualstocks.runtime_health import service_health_payload
from qualstocks.settings import Settings


OPEN_HYPOTHESIS_STATES = {
    "candidate",
    "active",
    "reinforced",
    "confirmed_by_norwegian_source",
    "exiting",
}


def build_dashboard_status(
    settings: Settings,
    *,
    read_model: dict[str, object] | None = None,
    services_error: str | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    timestamp = now or datetime.now(timezone.utc)
    model = read_model or {}
    active_hypothesis = _active_hypothesis(model.get("active_hypothesis"))
    paper_position = _paper_position(model.get("position"), model.get("valuation"))
    system_state = _system_state(
        active_hypothesis=active_hypothesis,
        paper_position=paper_position,
        services_error=services_error,
    )
    return {
        "system_state": system_state,
        "mode": "paper",
        "paper_trading_only": settings.paper_trading_only,
        "max_open_hypotheses": settings.max_open_hypotheses,
        "active_hypothesis": active_hypothesis,
        "source_health": _source_health(model.get("source_health"), timestamp),
        "latest_events": _list(model.get("latest_events")),
        "queue_status": model.get("queue_status") or _empty_queue_status(),
        "paper_position": paper_position,
        "planned_exits": _list(model.get("planned_exits")),
        "risk_decisions": _list(model.get("risk_decisions")),
        "audit_timeline": _list(model.get("audit_timeline")),
        "services": _services(settings, services_error),
    }


def _system_state(
    *,
    active_hypothesis: dict[str, object] | None,
    paper_position: dict[str, object] | None,
    services_error: str | None,
) -> str:
    if services_error:
        return "degraded"
    if active_hypothesis is None:
        return "listening"
    state = str(active_hypothesis.get("state") or "")
    if state == "confirmed_by_norwegian_source" and paper_position is not None:
        return "exit_scheduled"
    if state == "exiting":
        return "exiting"
    if state in OPEN_HYPOTHESIS_STATES:
        return "waiting_for_norwegian_confirmation"
    return "hypothesis_active"


def _active_hypothesis(value: object) -> dict[str, object] | None:
    row = _dict(value)
    if not row:
        return None
    return {
        "id": row.get("id"),
        "state": row.get("state"),
        "created_at": _iso(row.get("created_at")),
        "thesis": row.get("thesis"),
        "direction": row.get("direction"),
        "confidence": _number(row.get("confidence")),
        "confidence_label": _confidence_label(row.get("confidence")),
        "reasoning_summary": row.get("reasoning_summary") or row.get("thesis"),
        "evidence": _list(row.get("evidence")),
        "norwegian_confirmation": row.get("norwegian_confirmation")
        or _empty_norwegian_confirmation(),
        "reinforcement_conditions": _list(row.get("reinforcement_conditions")),
        "contradiction_conditions": _list(row.get("contradiction_conditions")),
    }


def _paper_position(position_value: object, valuation_value: object) -> dict[str, object] | None:
    position = _dict(position_value)
    if not position:
        return None
    quantity = _decimal_or_zero(position.get("quantity"))
    if quantity <= 0:
        return None

    valuation = _dict(valuation_value)
    return {
        "instrument": position.get("instrument") or valuation.get("instrument") or "EQNR.OL",
        "side": "long",
        "aum_allocated_pct": _number(position.get("aum_allocated_pct")),
        "tranches": _list(position.get("tranches")),
        "quantity": _number(quantity),
        "average_entry_price": _number(position.get("average_entry_price")),
        "realized_pnl": _number(_first_present(valuation, position, "realized_pnl")),
        "unrealized_pnl": _number(_first_present(valuation, position, "unrealized_pnl")),
        "last_price": _number(valuation.get("last_price")),
        "market_value": _number(valuation.get("market_value")),
        "unrealized_pnl_pct": _number(valuation.get("unrealized_pnl_pct")),
        "total_pnl": _number(valuation.get("total_pnl")),
        "total_pnl_pct": _number(valuation.get("total_pnl_pct")),
        "quote_freshness": valuation.get("quote_freshness") or "missing",
        "quote_source": valuation.get("quote_source"),
        "quote_observed_at": _iso(valuation.get("quote_observed_at")),
    }


def _source_health(value: object, now: datetime) -> list[dict[str, object]]:
    rows = _list(value)
    normalized = []
    for row_value in rows:
        row = _dict(row_value)
        last_event_at = _datetime(row.get("last_event_at"))
        normalized.append(
            {
                "source": row.get("source"),
                "source_class": row.get("source_class"),
                "status": row.get("status") or "unknown",
                "last_event_at": _iso(last_event_at),
                "last_checked_at": _iso(row.get("last_checked_at")),
                "last_error": row.get("last_error"),
                "lag_seconds": (
                    max(0, int((now - last_event_at).total_seconds()))
                    if last_event_at is not None
                    else None
                ),
            }
        )
    return normalized


def _services(settings: Settings, services_error: str | None) -> dict[str, object]:
    services = service_health_payload(settings)
    services["api"]["status"] = "degraded" if services_error else "healthy"
    return {
        **services,
        "supabase": (
            "degraded"
            if services_error
            else "configured"
            if settings.supabase_url
            else "missing_config"
        ),
        "openai": "configured" if settings.openai_api_key else "missing_config",
        "error": services_error,
    }


def _empty_queue_status() -> dict[str, int]:
    return {
        "queued": 0,
        "running": 0,
        "failed": 0,
    }


def _empty_norwegian_confirmation() -> dict[str, object]:
    return {
        "status": "waiting",
        "source": None,
        "first_seen_at": None,
        "url": None,
    }


def _first_present(
    first: dict[str, object],
    second: dict[str, object],
    key: str,
) -> object:
    return first.get(key) if first.get(key) is not None else second.get(key)


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _decimal_or_zero(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _confidence_label(value: object) -> str:
    confidence = _number(value)
    if confidence is None:
        return "unknown"
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.6:
        return "medium"
    return "low"


def _iso(value: object) -> str | None:
    parsed = _datetime(value)
    if parsed is None:
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def _datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
