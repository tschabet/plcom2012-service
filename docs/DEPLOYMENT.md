# Deployment

The service is stateless: no database, no volumes, no outbound connections. One container, port 8000.

## Build and run

```bash
docker build -t plcom2012-service .
docker run --rm -p 8000:8000 \
  -e PLCOM_CANONICAL_BASE=https://your-namespace.example/fhir \
  plcom2012-service
```

The image runs as a non-root user (uid 10001) and has a healthcheck on `GET /health`.
`docker-compose.yml` contains the same setup with commented Traefik labels.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `PLCOM_CANONICAL_BASE` | `https://example.org/fhir` | **Set to your own namespace** before the first real use. It appears in the Observation code system and in the reference Questionnaire. |
| `PLCOM_API_KEY` | unset | If set, `POST` requires `X-API-Key`. `GET /health` and the reference Questionnaire stay open. |
| `PLCOM_LINKID_MAP` | unset | JSON file (mounted into the container) to map your own questionnaire linkIds, see README. |
| `PLCOM_MAX_BODY_BYTES` | `262144` | Request size limit (413 above). |

## Reverse proxy

Terminate TLS and apply rate limiting at the proxy; the service itself has none. The service does not
log request bodies, make sure the proxy does not either. Behind Traefik, a `rateLimit` middleware and
the compose labels are enough, no sticky sessions or shared state are needed (horizontal scaling is
trivial).

## Public test endpoint

- Only synthetic data. Say so wherever the URL is published; `GET /` already returns a warning.
- Decide whether the test instance is open (rate-limited) or protected by `PLCOM_API_KEY` / your SSO.
- `/docs` (OpenAPI UI) is public by default; that is usually wanted on a test instance.

## Acceptance test

```bash
BASE_URL=https://plcom.example.org [API_KEY=...] scripts/smoke_test.sh
```

Checks health, the reference Questionnaire, both output modes, the 400 and 422 error paths and, if
`API_KEY` is set, the 401. Exit code is non-zero on any failure.

## Notes

- The `Dockerfile` has not been built in CI yet; the first build on the target is the first real test.
- The image build is pinned: the `Dockerfile` installs with `pip install -c constraints.txt .`. The file
  was taken from `pip freeze` of a verified build on `python:3.12-slim` (smoke test: ALL OK; the pinned
  build was reproduced on a second host). `pyproject.toml` stays lower-bounded, and CI and local
  development stay unpinned on purpose. To update the pins: build without them, run `pip freeze` in
  the container (without the `plcom2012-service` line), run `scripts/smoke_test.sh`, then commit the
  new file. The base image tag `python:3.12-slim` itself is not pinned.
- Not a certified medical device, see README.
