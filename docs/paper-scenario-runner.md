# Paper Trading Scenario Runner

The paper scenario runner is the deterministic dry-run harness for V1. It starts
from `RawAdapterEvent` fixtures and exercises the same path real sources should
use:

1. raw adapter event ingestion
2. normalization and idempotency handling
3. queued analysis result represented by a classification fixture
4. hypothesis lifecycle decision
5. risk gate decision
6. paper order, fill, valuation, and planned exit handling
7. dashboard-status read model generation

Use it when changing source adapters, strategy lifecycle behavior, risk rules,
paper ledger behavior, or dashboard status mapping.

The runner does not call live networks or OpenAI. Classification is supplied as
a fixture so scenario tests stay deterministic and cheap.

The default scenario surface supports:

- first signal opens the initial 50 percent paper tranche.
- independent reinforcement opens the second tranche.
- Norwegian confirmation records 30/40/50 minute planned exits.
- timer steps execute scheduled or fallback exits.
- duplicate raw events are ingested once and not traded twice.
- contradiction classifications close the paper position and reset the active
  hypothesis.
