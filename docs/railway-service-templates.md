# Railway Service Templates

`railway/service-templates.json` is the checked-in deployment template for the
three Railway services.

It intentionally stores service names, start commands, health endpoints, and
required variable names only. It must never contain secret values.

## Services

Use one Railway project with three services from the same GitHub repository:

- `api-service`
- `watcher-service`
- `worker-service`

Set each service's start command from `railway/service-templates.json`.

## Manual Railway UI Steps

These remain manual because Railway service creation and Doppler sync are
environment-specific:

- Create each service in the Railway project.
- Link each service to the GitHub repo and branch.
- Set the service-specific start command.
- Attach Doppler-synced shared variables to each service.
- For `watcher-service`, include `WATCHER_BACKOFF_INITIAL_SECONDS` and
  `WATCHER_BACKOFF_MAX_SECONDS` so polling-source retry behavior can be tuned
  without code changes.
- Configure health checks for API endpoints where Railway supports HTTP health
  checks.
- Confirm deploy logs show startup validation output.

## Verification

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_railway_templates
```

The tests verify:

- expected service names and start commands
- importable service entry-point modules when dependencies are installed
- template values contain variable names, not secrets
- every service includes the paper-only live gate variables
