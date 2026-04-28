# Observability and Metrics

## Built-in telemetry surfaces

- request-level observability middleware
- health and service health endpoints
- diagnostics config and route inventory
- metrics endpoints for SLO and context efficiency

## Operator checks

```bash
curl http://localhost:8000/metrics
curl http://localhost:8000/metrics/slo
curl http://localhost:8000/metrics/context-efficiency
syncore metrics context
```

## Suggested dashboards

Track over time:
- API error rates
- p95 latency
- run success/failure ratios
- context savings trend by profile/mode
