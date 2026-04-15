# Security Policy

## Supported Versions

Only the latest release of TraceAI receives security fixes. We encourage all users to keep up to date.

| Version | Supported |
|---|:---:|
| 0.5.x (latest) | ✅ |
| < 0.5.0 | ❌ |

---

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you have found a vulnerability, report it privately by opening a [GitHub Security Advisory](https://github.com/arnavvj/traceai/security/advisories/new). This keeps the details confidential until a fix is released.

Include as much of the following as possible:

- A description of the vulnerability and its potential impact
- Steps to reproduce (minimal reproduction script if possible)
- The version of TraceAI affected
- Any suggested fix or mitigation you are aware of

You will receive a response within **72 hours** acknowledging receipt. We aim to release a fix or mitigation within **14 days** for confirmed high-severity issues, and will keep you informed of progress.

---

## Scope

TraceAI is a **local-first developer tool**. It is designed to run on a developer's own machine and is not intended to be exposed to the public internet without additional hardening (a reverse proxy, authentication layer, etc.).

Issues that are **in scope** for this policy:

- Code execution vulnerabilities in the TraceAI Python package (`traceai/`)
- Vulnerabilities in the FastAPI server (`traceai/server.py`) when accessed over a local or private network
- Vulnerabilities in the React dashboard (`dashboard/`) that could affect users who access the dashboard
- Supply-chain issues with direct dependencies listed in `pyproject.toml`
- Path traversal or file read/write issues in the CLI or storage layer
- Injection vulnerabilities (SQL, command) in the storage or API layers

Issues that are **out of scope**:

- Vulnerabilities that require physical access to the machine running TraceAI
- Attacks that require a malicious API key or provider response already under attacker control
- Vulnerabilities in transitive dependencies that do not have a practical exploit path through TraceAI
- Denial-of-service via intentional resource exhaustion of the local SQLite database
- Security issues in the user's own provider keys or network configuration

---

## Security Design Notes

### Data stays local

All trace data is stored in a local SQLite file (`~/.traceai/traces.db` by default). TraceAI never sends traces, prompts, model responses, or metadata to any external server. The only outbound network calls are the LLM API calls you explicitly make through your own instrumented code.

### API keys

TraceAI never reads, stores, or logs API keys. Keys are consumed directly by the underlying provider SDKs (`openai`, `anthropic`) through standard environment variable lookup. The `GET /api/providers` endpoint returns only a boolean (key present / absent) — the key value is never transmitted to the frontend.

### Local server

The dashboard server (`traceai open`) binds to `localhost` by default. It should **not** be exposed to public networks without authentication. If you need remote access, place it behind a reverse proxy with authentication (e.g., nginx + HTTP basic auth, Tailscale, SSH tunnel).

### SQLite injection

All database queries use parameterised statements. User-supplied strings (trace IDs, search queries, tag values) are never interpolated directly into SQL.

### Dashboard XSS

Span inputs, outputs, and metadata are rendered through React's `JSON.stringify` + a controlled JSON viewer component. Raw HTML from trace content is never injected into the DOM.

---

## Disclosure Policy

Once a vulnerability is confirmed and a fix is available:

1. A patched release is published to PyPI.
2. A [GitHub Security Advisory](https://github.com/arnavvj/traceai/security/advisories) is published with full details.
3. The [CHANGELOG.md](CHANGELOG.md) entry for the release notes the fix.

We follow a **coordinated disclosure** model — we ask reporters to keep details confidential until the fix is released, and we credit reporters by name (or handle) in the advisory unless they prefer to remain anonymous.
