# Strategy Worker Boundary

`PaperStrategyService` is the bridge from completed AI classifications to the
paper-trading lifecycle.

The service:

- refuses to run when `paper_trading_only` is false
- loads the current active hypothesis from persistence
- runs `StrategyOrchestrator.handle_classification`
- persists newly opened hypotheses
- persists risk decisions, paper orders, fills, position snapshots, valuations,
  and orchestrator audit events

Use `build_paper_strategy_service(settings, repository)` to wire runtime settings
into the lifecycle and risk configs. In particular, the first order uses
`TRANCHE_ONE_AUM_PCT`, the second order uses `TRANCHE_TWO_AUM_PCT`, and exits
use `EXIT_WINDOWS_MINUTES`.

The service is intentionally a paper-only boundary. Live broker execution should
be added behind a separate reviewed execution provider and explicit live gates.
