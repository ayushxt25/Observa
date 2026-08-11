# Observa v1.0.0 Release Checklist

- [ ] Clean `develop` working tree before release commit.
- [ ] Clean Docker database rebuild reaches Alembic head `0009_incident_events`.
- [ ] Backend tests pass: `python -m pytest`.
- [ ] Frontend lint/typecheck/tests/build pass.
- [ ] Bundle size recorded with `npm run analyze:size`.
- [ ] Docker config validates and services are healthy.
- [ ] Browser smoke covers auth, dashboard, service catalog, alerts/incidents, topology, audit, and incident intelligence.
- [ ] Concurrency checks pass for alert open/resolve and notification idempotency.
- [ ] Secret leak scan confirms no raw passwords, API keys, refresh tokens, JWTs, webhook secrets, or SMTP credentials in durable logs/tables.
- [ ] README, backend docs, telemetry API docs, changelog, and limitations are current.
- [ ] Screenshots contain no test credentials or secrets.
- [ ] Deployment environment variables are reviewed before tagging.
- [ ] Tag `v1.0.0` only after final report review.
