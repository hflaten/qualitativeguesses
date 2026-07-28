from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from qualstocks.dashboard import build_dashboard_status
from qualstocks.ingestion import PsycopgDatabaseClient
from qualstocks.settings import load_settings

app = FastAPI(title="Qualitative Guesses", version="0.1.0")


@app.get("/health")
def health() -> dict[str, object]:
    settings = load_settings()
    return {"ok": True, **settings.public_status}


@app.get("/api/status")
def api_status() -> dict[str, object]:
    settings = load_settings()
    read_model: dict[str, object] | None = None
    services_error = None
    if settings.source_persistence_backend == "postgres" and settings.supabase_db_url:
        try:
            client = PsycopgDatabaseClient(settings.supabase_db_url)
            read_model = client.fetch_dashboard_read_model()
        except Exception as exc:
            services_error = f"dashboard read model unavailable: {exc}"
    return build_dashboard_status(
        settings,
        read_model=read_model,
        services_error=services_error,
    )


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
            color-scheme: light dark;
            font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: Canvas;
            color: CanvasText;
          }
          body { margin: 0; padding: 28px; }
          main { max-width: 980px; margin: 0 auto; display: grid; gap: 18px; }
          section { border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 8px; padding: 16px; }
          h1, h2 { margin: 0; font-weight: 600; }
          h1 { font-size: 1.5rem; }
          h2 { font-size: 1rem; }
          .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
          .card { border: 1px solid color-mix(in srgb, CanvasText 14%, transparent); border-radius: 8px; padding: 12px; min-height: 92px; }
          .muted { color: color-mix(in srgb, CanvasText 62%, transparent); }
          .status { font-weight: 600; }
          @media (max-width: 760px) { body { padding: 16px; } .grid { grid-template-columns: 1fr; } }
        </style>
      </head>
      <body>
        <main>
          <header>
            <h1>Qualitative Guesses</h1>
            <p class="muted">Paper-trading operator dashboard for Equinor event hypotheses.</p>
          </header>
          <section>
            <h2>System Status</h2>
            <p class="status">Listening</p>
            <p class="muted">No active hypothesis. Paper trading only.</p>
          </section>
          <section class="grid">
            <div class="card">
              <h2>Active Hypothesis</h2>
              <p class="muted">None. The system is waiting for qualified source events.</p>
            </div>
            <div class="card">
              <h2>Source Watchers</h2>
              <p class="muted">Watcher service scaffold pending source adapters.</p>
            </div>
            <div class="card">
              <h2>Paper Position</h2>
              <p class="muted">No open paper position.</p>
            </div>
          </section>
          <section>
            <h2>Audit Timeline</h2>
            <p class="muted">Events, AI classifications, risk decisions, paper orders, and exits will appear here.</p>
          </section>
        </main>
      </body>
    </html>
    """
