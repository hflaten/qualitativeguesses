from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from qualstocks.dashboard import build_dashboard_status
from qualstocks.ingestion import PsycopgDatabaseClient
from qualstocks.runtime_health import (
    ServiceName,
    service_health_payload,
    validate_service_startup,
)
from qualstocks.settings import load_settings

app = FastAPI(title="Qualitative Guesses", version="0.1.0")


@app.on_event("startup")
def validate_api_startup() -> None:
    settings = load_settings()
    validate_service_startup(settings, ServiceName.API).raise_for_errors()


@app.get("/health")
def health() -> dict[str, object]:
    settings = load_settings()
    startup = validate_service_startup(settings, ServiceName.API)
    return {
        "ok": startup.ok,
        **settings.public_status,
        "startup": startup.as_log_payload(),
        "services": service_health_payload(settings),
    }


@app.get("/api/status")
def api_status() -> dict[str, object]:
    settings, read_model, services_error = _dashboard_inputs()
    return build_dashboard_status(
        settings,
        read_model=read_model,
        services_error=services_error,
    )


@app.get("/api/timeline")
def api_timeline() -> dict[str, object]:
    settings, read_model, services_error = _dashboard_inputs()
    status = build_dashboard_status(
        settings,
        read_model=read_model,
        services_error=services_error,
    )
    return {
        "system_state": status["system_state"],
        "paper_position": status["paper_position"],
        "event_timeline": status["event_timeline"],
    }


def _dashboard_inputs() -> tuple[object, dict[str, object] | None, str | None]:
    settings = load_settings()
    read_model: dict[str, object] | None = None
    services_error = None
    if settings.source_persistence_backend == "postgres" and settings.supabase_db_url:
        try:
            client = PsycopgDatabaseClient(settings.supabase_db_url)
            read_model = client.fetch_dashboard_read_model()
        except Exception as exc:
            services_error = f"dashboard read model unavailable: {exc}"
    return settings, read_model, services_error


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Qualitative Guesses</title>
        <style>
          :root {
            font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f6f7f3;
            color: #202420;
            --border: #d8ddd2;
            --muted: #636b61;
            --panel: #ffffff;
            --good: #0f766e;
            --warn: #a16207;
            --bad: #b42318;
          }
          body { margin: 0; padding: 20px; }
          main { max-width: 1180px; margin: 0 auto; display: grid; gap: 14px; }
          header { display: flex; justify-content: space-between; gap: 16px; align-items: end; }
          section, .card { border: 1px solid var(--border); border-radius: 8px; background: var(--panel); }
          section { padding: 14px; }
          h1, h2, h3, p { margin: 0; }
          h1 { font-size: 1.5rem; }
          h2 { font-size: .9rem; text-transform: uppercase; color: var(--muted); }
          h3 { font-size: 1rem; }
          .muted { color: var(--muted); }
          .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }
          .span-4 { grid-column: span 4; }
          .span-6 { grid-column: span 6; }
          .span-8 { grid-column: span 8; }
          .span-12 { grid-column: span 12; }
          .card { padding: 14px; display: grid; gap: 10px; min-width: 0; }
          .metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
          .metric { border-top: 1px solid var(--border); padding-top: 10px; min-width: 0; }
          .label { color: var(--muted); font-size: .78rem; }
          .value { font-size: 1.18rem; font-weight: 650; overflow-wrap: anywhere; }
          .pill { display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 5px 9px; background: #eef1eb; font-size: .82rem; }
          .fresh { color: var(--good); }
          .stale { color: var(--warn); }
          .missing, .degraded { color: var(--bad); }
          .positive { color: var(--good); }
          .negative { color: var(--bad); }
          .list { display: grid; gap: 8px; }
          .row { border-top: 1px solid var(--border); padding-top: 8px; display: grid; gap: 3px; }
          .empty { color: var(--muted); font-size: .92rem; }
          @media (max-width: 860px) {
            body { padding: 12px; }
            header { display: grid; }
            .span-4, .span-6, .span-8 { grid-column: span 12; }
            .metrics { grid-template-columns: 1fr 1fr; }
          }
          @media (max-width: 520px) { .metrics { grid-template-columns: 1fr; } }
        </style>
      </head>
      <body>
        <main>
          <header>
            <div>
              <h1>Qualitative Guesses</h1>
              <p class="muted">Equinor paper trader</p>
            </div>
            <div id="updated" class="muted">Connecting</div>
          </header>
          <section class="grid">
            <div class="card span-4">
              <h2>State</h2>
              <div id="state" class="value">Loading</div>
              <div id="mode" class="muted">Paper</div>
            </div>
            <div class="card span-8">
              <h2>Position</h2>
              <div id="position-summary" class="value">No open position</div>
              <div id="quote" class="pill missing">quote missing</div>
              <div id="position-metrics" class="metrics"></div>
            </div>
            <div class="card span-6">
              <h2>Hypothesis</h2>
              <div id="hypothesis" class="list"></div>
            </div>
            <div class="card span-6">
              <h2>Sources</h2>
              <div id="sources" class="list"></div>
            </div>
            <div class="card span-6">
              <h2>Risk Decisions</h2>
              <div id="risk" class="list"></div>
            </div>
            <div class="card span-6">
              <h2>Planned Exits</h2>
              <div id="exits" class="list"></div>
            </div>
            <div class="card span-12">
              <h2>Timeline</h2>
              <div id="timeline" class="list"></div>
            </div>
            <div class="card span-6">
              <h2>Latest Events</h2>
              <div id="events" class="list"></div>
            </div>
            <div class="card span-6">
              <h2>Audit</h2>
              <div id="audit" class="list"></div>
            </div>
          </section>
        </main>
        <script>
          const fmt = new Intl.NumberFormat("nb-NO", { maximumFractionDigits: 2 });
          const money = value => value == null ? "n/a" : `${fmt.format(value)} NOK`;
          const pct = value => value == null ? "n/a" : `${fmt.format(value)}%`;
          const esc = value => String(value).replace(/[&<>"']/g, char => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            "\"": "&quot;",
            "'": "&#39;"
          })[char]);
          const text = value => value == null || value === "" ? "n/a" : esc(value);
          const cls = value => value > 0 ? "positive" : value < 0 ? "negative" : "";

          function metric(label, value, className = "") {
            return `<div class="metric"><div class="label">${label}</div><div class="value ${className}">${value}</div></div>`;
          }

          function empty(label) {
            return `<div class="empty">${label}</div>`;
          }

          function rows(items, render, emptyLabel) {
            return items && items.length ? items.map(render).join("") : empty(emptyLabel);
          }

          function render(data) {
            document.getElementById("updated").textContent = new Date().toLocaleTimeString("nb-NO");
            document.getElementById("state").textContent = text(data.system_state);
            document.getElementById("mode").textContent = data.paper_trading_only ? "Paper only" : "Live disabled";

            const position = data.paper_position;
            const quote = document.getElementById("quote");
            if (position) {
              document.getElementById("position-summary").textContent = `${position.instrument} long`;
              quote.textContent = `${position.quote_freshness} · ${text(position.quote_source)}`;
              quote.className = `pill ${position.quote_freshness || "missing"}`;
              document.getElementById("position-metrics").innerHTML = [
                metric("Last price", money(position.last_price)),
                metric("Market value", money(position.market_value)),
                metric("Unrealized P/L", money(position.unrealized_pnl), cls(position.unrealized_pnl)),
                metric("Unrealized %", pct(position.unrealized_pnl_pct), cls(position.unrealized_pnl_pct)),
                metric("Realized P/L", money(position.realized_pnl), cls(position.realized_pnl)),
                metric("Total P/L", money(position.total_pnl), cls(position.total_pnl)),
              ].join("");
            } else {
              document.getElementById("position-summary").textContent = "No open position";
              quote.textContent = "quote missing";
              quote.className = "pill missing";
              document.getElementById("position-metrics").innerHTML = "";
            }

            const hypothesis = data.active_hypothesis;
            const confidence = hypothesis?.confidence == null ? null : hypothesis.confidence * 100;
            document.getElementById("hypothesis").innerHTML = hypothesis ? `
              <div class="row">
                <h3>${text(hypothesis.thesis)}</h3>
                <div class="muted">${text(hypothesis.state)} · ${pct(confidence)}</div>
                <p>${text(hypothesis.reasoning_summary)}</p>
              </div>` : empty("No active hypothesis");

            document.getElementById("sources").innerHTML = rows(
              data.source_health,
              item => `<div class="row"><h3>${text(item.source)}</h3><div class="muted">${text(item.status)} · lag ${text(item.lag_seconds)}s</div></div>`,
              "No source health yet"
            );
            document.getElementById("risk").innerHTML = rows(
              data.risk_decisions,
              item => `<div class="row"><h3>${text(item.status)}</h3><div>${text(item.reason)}</div><div class="muted">${text(item.created_at)}</div></div>`,
              "No risk decisions yet"
            );
            document.getElementById("exits").innerHTML = rows(
              data.planned_exits,
              item => `<div class="row"><h3>${text(item.status)}</h3><div class="muted">${text(item.window_minutes)} min · ${text(item.scheduled_for)}</div></div>`,
              "No planned exits"
            );
            document.getElementById("timeline").innerHTML = rows(
              data.event_timeline,
              item => `<div class="row"><h3>${text(item.title)}</h3><div class="muted">${text(item.timestamp)} · ${text(item.type)} · ${text(item.source)} · ${text(item.severity)}</div></div>`,
              "No timeline entries yet"
            );
            document.getElementById("events").innerHTML = rows(
              data.latest_events,
              item => `<div class="row"><h3>${text(item.title)}</h3><div class="muted">${text(item.source)} · ${text(item.first_seen_at)}</div></div>`,
              "No events yet"
            );
            document.getElementById("audit").innerHTML = rows(
              data.audit_timeline,
              item => `<div class="row"><h3>${text(item.action)}</h3><div>${text(item.summary)}</div><div class="muted">${text(item.created_at)}</div></div>`,
              "No audit entries yet"
            );
          }

          async function refresh() {
            try {
              const response = await fetch("/api/status");
              render(await response.json());
            } catch (error) {
              document.getElementById("state").textContent = "degraded";
              document.getElementById("updated").textContent = String(error);
            }
          }

          refresh();
          setInterval(refresh, 3000);
        </script>
      </body>
    </html>
    """
