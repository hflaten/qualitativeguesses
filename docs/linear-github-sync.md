# Linear and GitHub Sync

## Purpose

This note records the verified integration behavior between Linear project
`Event-Triggered Trading Platform` and GitHub repository
`hflaten/qualitativeguesses`.

## Confirmed Integration

Linear can see GitHub activity for the repository. Recent PRs with QUA issue
keys were attached back to their Linear issues, including:

- QUA-42: GitHub PR #31.
- QUA-43: GitHub PR #30.
- QUA-5: GitHub PR #32.
- QUA-8: GitHub PR #33.
- QUA-9: GitHub PR #34.

The Linear issue QUA-6 also links the GitHub repository and Linear GitHub
integration settings page.

## Branch Convention

Use:

```text
qua-<issue-number>-<short-slug>
```

Examples:

- `qua-42-backtest-dataset-loader`
- `qua-43-railway-health-guards`
- `qua-9-linear-issue-template`

Commits and PR titles should start with the Linear issue key:

```text
QUA-42 Add historical backtest dataset loader
```

## Expected Workflow

1. Move the Linear issue to `In Progress`.
2. Create the QUA-prefixed branch.
3. Commit with a QUA-prefixed message.
4. Open a PR with a QUA-prefixed title.
5. Merge after verification.
6. Comment on the Linear issue with PR link and verification.
7. Move the issue to `Done`.

## Known Limitation

GitHub PR links attach to Linear issues, but the final Linear status and
completion evidence should still be updated explicitly by Codex. Do not rely on
GitHub automation alone to mark issue acceptance complete.
