# Dashboard Live-State API Contract

## Purpose

The dashboard should answer the operator's live questions in plain language:

- What did the system hear?
- What does it think happened?
- Why does it matter for Equinor?
- Did it paper trade?
- How much paper AUM is allocated?
- When will it exit?
- What would reinforce, contradict, or cancel the hypothesis?

The first API contract should be stable enough for the dashboard to render from
mock data before Supabase queries are wired in.

## Endpoint

```text
GET /api/status
```

The endpoint returns the current paper-trading system state.

## Top-level shape

```json
{
  "system_state": "listening",
  "mode": "paper",
  "paper_trading_only": true,
  "max_open_hypotheses": 1,
  "active_hypothesis": null,
  "source_health": [],
  "paper_position": null,
  "planned_exits": [],
  "audit_timeline": [],
  "event_timeline": []
}
```

## Fields

### `system_state`

Human-readable machine state.

Allowed V1 values:

- `listening`
- `hypothesis_active`
- `reinforced`
- `waiting_for_norwegian_confirmation`
- `exit_scheduled`
- `exiting`
- `exited`
- `degraded`

### `mode`

Execution mode. V1 must return:

```json
"paper"
```

### `active_hypothesis`

Null when idle. Otherwise:

```json
{
  "id": "hyp_123",
  "state": "active",
  "created_at": "2026-07-27T12:03:15Z",
  "thesis": "US-Iran escalation increases oil supply risk, likely positive for Equinor short-term.",
  "direction": "bullish_equinor",
  "confidence": 0.82,
  "confidence_label": "high",
  "reasoning_summary": "Official actor signal indicates escalation; oil supply risk channel is relevant to Equinor.",
  "evidence": [
    {
      "source": "CENTCOM",
      "source_class": "official_actor",
      "title": "Statement on regional military activity",
      "first_seen_at": "2026-07-27T12:03:11Z",
      "url": "https://example.invalid/centcom",
      "role": "trigger"
    }
  ],
  "norwegian_confirmation": {
    "status": "waiting",
    "source": null,
    "first_seen_at": null,
    "url": null
  },
  "reinforcement_conditions": [
    "Independent official confirmation",
    "Prediction-market probability move in same direction",
    "Brent move confirms oil shock channel"
  ],
  "contradiction_conditions": [
    "Official de-escalation statement",
    "Norwegian source frames event as immaterial to Equinor",
    "Brent reverses sharply before confirmation"
  ]
}
```

### `source_health`

One row per enabled source or source group:

```json
{
  "source": "Polymarket",
  "source_class": "prediction_market",
  "source_id": "polymarket_hormuz",
  "status": "online",
  "last_event_at": "2026-07-27T12:07:44Z",
  "last_checked_at": "2026-07-27T12:08:00Z",
  "last_error": null,
  "lag_seconds": 16
}
```

Allowed status values:

- `unknown`
- `online`
- `degraded`
- `offline`

### `paper_position`

Null when no paper position is open. Otherwise:

```json
{
  "instrument": "EQNR.OL",
  "side": "long",
  "aum_allocated_pct": 50,
  "tranches": [
    {
      "name": "tranche_1",
      "aum_pct": 50,
      "status": "filled",
      "order_id": "ord_123",
      "filled_at": "2026-07-27T12:03:18Z",
      "fill_price": 312.45
    }
  ],
  "quantity": 100,
  "average_entry_price": 312.45,
  "last_price": 330.12,
  "market_value": 33012,
  "unrealized_pnl": 1767,
  "unrealized_pnl_pct": 5.65,
  "realized_pnl": 0,
  "total_pnl": 1767,
  "total_pnl_pct": 1.77,
  "quote_freshness": "fresh",
  "quote_source": "yahoo:EQNR.OL",
  "quote_observed_at": "2026-07-27T12:08:00Z"
}
```

Allowed quote freshness values:

- `fresh`
- `stale`
- `missing`

### `planned_exits`

Exit candidates relative to the configured anchor:

```json
[
  {
    "window_minutes": 30,
    "anchor": "norwegian_confirmation",
    "scheduled_for": "2026-07-27T12:44:02Z",
    "status": "scheduled"
  },
  {
    "window_minutes": 40,
    "anchor": "norwegian_confirmation",
    "scheduled_for": "2026-07-27T12:54:02Z",
    "status": "scheduled"
  },
  {
    "window_minutes": 50,
    "anchor": "norwegian_confirmation",
    "scheduled_for": "2026-07-27T13:04:02Z",
    "status": "scheduled"
  }
]
```

Allowed statuses:

- `waiting_for_anchor`
- `scheduled`
- `executed`
- `cancelled`
- `missed`

### `audit_timeline`

Chronological operator-readable events:

```json
{
  "created_at": "2026-07-27T12:03:17Z",
  "action": "paper_order_approved",
  "summary": "Tranche 1 paper buy approved after official escalation signal.",
  "source": "risk_gate",
  "hypothesis_id": "hyp_123",
  "event_id": "evt_123"
}
```

### `event_timeline`

Unified operator timeline derived from source ingestion, duplicate/rejected
ingestion results, active hypothesis state, risk decisions, and audit entries.
Duplicate and rejected rows come from the durable `ingestion_outcomes` table.

```json
{
  "timestamp": "2026-07-27T12:03:17Z",
  "type": "paper_order_approved",
  "severity": "info",
  "source": "risk_gate",
  "title": "Tranche 1 paper buy approved after official escalation signal.",
  "entity_id": "evt_123"
}
```

Allowed V1 severities:

- `info`
- `warning`
- `error`

The feed is sorted newest-first. `/api/status` returns it alongside live P&L,
and `/api/timeline` returns a compact payload with `system_state`,
`paper_position`, and `event_timeline`.

## Idle example

```json
{
  "system_state": "listening",
  "mode": "paper",
  "paper_trading_only": true,
  "max_open_hypotheses": 1,
  "active_hypothesis": null,
  "source_health": [
    {
      "source": "GDELT",
      "source_class": "osint",
      "status": "online",
      "last_event_at": null,
      "last_checked_at": "2026-07-27T12:00:00Z",
      "last_error": null,
      "lag_seconds": null
    }
  ],
  "paper_position": null,
  "planned_exits": [],
  "audit_timeline": []
}
```

## Active example

```json
{
  "system_state": "waiting_for_norwegian_confirmation",
  "mode": "paper",
  "paper_trading_only": true,
  "max_open_hypotheses": 1,
  "active_hypothesis": {
    "id": "hyp_123",
    "state": "active",
    "created_at": "2026-07-27T12:03:15Z",
    "thesis": "US-Iran escalation increases oil supply risk, likely positive for Equinor short-term.",
    "direction": "bullish_equinor",
    "confidence": 0.82,
    "confidence_label": "high",
    "reasoning_summary": "Official actor signal indicates escalation; oil supply risk channel is relevant to Equinor.",
    "evidence": [
      {
        "source": "CENTCOM",
        "source_class": "official_actor",
        "title": "Statement on regional military activity",
        "first_seen_at": "2026-07-27T12:03:11Z",
        "url": "https://example.invalid/centcom",
        "role": "trigger"
      }
    ],
    "norwegian_confirmation": {
      "status": "waiting",
      "source": null,
      "first_seen_at": null,
      "url": null
    },
    "reinforcement_conditions": [
      "Independent official confirmation",
      "Prediction-market probability move in same direction",
      "Brent move confirms oil shock channel"
    ],
    "contradiction_conditions": [
      "Official de-escalation statement",
      "Norwegian source frames event as immaterial to Equinor",
      "Brent reverses sharply before confirmation"
    ]
  },
  "source_health": [],
  "paper_position": {
    "instrument": "EQNR.OL",
    "side": "long",
    "aum_allocated_pct": 50,
    "tranches": [
      {
        "name": "tranche_1",
        "aum_pct": 50,
        "status": "filled",
        "order_id": "ord_123",
        "filled_at": "2026-07-27T12:03:18Z",
        "fill_price": 312.45
      }
    ],
    "quantity": 100,
    "average_entry_price": 312.45,
    "unrealized_pnl": 0,
    "realized_pnl": 0
  },
  "planned_exits": [
    {
      "window_minutes": 30,
      "anchor": "norwegian_confirmation",
      "scheduled_for": null,
      "status": "waiting_for_anchor"
    }
  ],
  "audit_timeline": [
    {
      "created_at": "2026-07-27T12:03:17Z",
      "action": "paper_order_approved",
      "summary": "Tranche 1 paper buy approved after official escalation signal.",
      "source": "risk_gate",
      "hypothesis_id": "hyp_123",
      "event_id": "evt_123"
    }
  ]
}
```

## Implementation notes

- Keep summaries human-readable and short.
- Do not expose secrets, raw signed webhook headers, or service-role details.
- Prefer null over invented values when a field is not known yet.
- Keep V1 explicitly paper trading only in every response.
