# Codex, Linear, and GitHub Workflow

## Purpose

This document defines how planning, implementation, review, and release history
move through Codex, Linear, and GitHub for the event-triggered trading platform.

## Sources of Truth

- Product plan, priorities, and acceptance criteria live in Linear project
  `Event-Triggered Trading Platform`.
- Durable architecture decisions, runtime contracts, and operational procedures
  live in repository documentation under `docs/`.
- Code, migrations, tests, and release history live in GitHub repository
  `hflaten/qualitativeguesses`.
- Secrets live in Doppler and are synced into Railway. Secrets must not be
  copied into Linear, GitHub issues, commits, or PR descriptions.
- Linear issue comments are the implementation log for each task: what changed,
  verification evidence, PR links, and remaining risks.

## Ticket Creation

Codex should create or refine Linear tickets when work needs implementation,
research, operational follow-up, or a durable decision that should be tracked
beyond the current chat.

Tickets can be created manually when the user is capturing raw ideas, rough
priorities, or non-technical planning. Before implementation starts, Codex should
make the ticket specific enough to execute.

Each implementation ticket should include:

- context and intended behavior;
- explicit scope and affected components;
- acceptance criteria;
- test or verification expectations;
- safety and live-trading risk notes where relevant;
- branch hint using the `QUA-<number>` issue key.

Use `docs/linear-issue-template.md` when creating or refining tickets.

Split tickets when one issue would require unrelated write scopes, different
owners, or separate design decisions. Keep a ticket together when the work
shares one public contract or must be integrated atomically.

## Issue Start Checklist

Before changing files for a Linear issue:

1. Confirm the target issue ID and current Linear status.
2. Move the issue to `In Progress`.
3. Sync local `main` with GitHub.
4. Create a branch named `qua-<issue-number>-<short-slug>`.
5. Read nearby docs, code, and tests before editing.
6. Keep the write scope aligned with the issue.

## Branch, Commit, and PR Naming

- Branches use `qua-<issue-number>-<short-slug>`, for example
  `qua-42-backtest-dataset-loader`.
- Commits start with the Linear key, for example
  `QUA-42 Add historical backtest dataset loader`.
- PR titles start with the Linear key and summarize the outcome.
- PR bodies include summary, verification, and known limitations.
- One branch and PR should map to one Linear issue unless a senior decision
  explicitly groups tiny documentation-only work.

## Implementation Loop

During implementation, Codex should:

- prefer existing repository patterns over new abstractions;
- keep changes scoped to the issue;
- add or update tests proportional to risk;
- run focused tests before full verification;
- avoid live network calls in tests;
- keep paper-trading safety explicit when touching trading behavior;
- avoid modifying secrets, generated credentials, or unrelated user work.

If implementation reveals a new design decision, Codex should stop, summarize the
choice, and ask for direction before widening the scope.

## Verification

Use these baseline commands before opening a PR:

```bash
PYTHONPATH=src make test
PYTHONPATH=src make typecheck
make lint
git diff --check
```

If a check cannot run locally, record the exact reason in the PR and Linear
comment. As of this workflow, local `make lint` may fail when `ruff` is not
installed; CI installs dev dependencies and should run it when configured.

## PR and Merge Flow

Codex should open a ready PR after local verification unless the user asked for a
draft. The PR should link naturally to the Linear issue through the issue key in
branch, commit, and title.

Merge only after:

- acceptance criteria are met;
- local verification is recorded;
- CI or repository checks are green, unavailable, or explicitly documented;
- no unresolved review feedback remains.

After merge, Codex should fast-forward local `main` before starting the next
issue.

## Issue Finish Checklist

When a PR is merged:

1. Comment on the Linear issue with the PR link.
2. Summarize implemented behavior.
3. List tests and checks run, including failures or skipped checks.
4. Mention remaining risks or follow-up tickets.
5. Move the issue to `Done`.
6. Return to `main` and pull the merge commit.

## Parallel Agent Policy

Use `docs/agent-execution-policy.md` for decomposition and parallel-agent rules.
Senior agents own design decisions, issue slicing, shared contracts, and final
acceptance. Smaller agents may implement bounded slices only when their write
scope and verification expectations are explicit.
