# Setup & data

[← TRENCHNET](../README.md)

## Run locally

Requires Python 3.11+. The application runtime has no third-party Python or Node dependencies.

```sh
python3 server.py
```

Open http://127.0.0.1:8787. SQLite is initialized automatically. The background collector repeats after approximately 90 seconds plus request time. New installations have no live database or fabricated market rows bundled with them. Upstream failures may leave an empty or partial sample.

The published source and current hosted UI are not identical; see [version scope](SHOWCASE.md#hosted-app-and-repository-scope). Running this repository does not deploy a site or start the Telegram worker.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | Bind address; the Docker image uses `0.0.0.0` |
| `PORT` | `8787` | HTTP port |
| `DB_PATH` | `data/trenchnet.sqlite` beside the source | Application SQLite path |
| `COLLECT_INTERVAL` | `90` | Seconds between collection cycles, with a minimum of 90 |
| `COLLECT_ENABLED` | `1` | Set to `0` to disable background collection |
| `TRUST_CLOUDFLARE` | unset | `1` trusts Cloudflare client-IP headers only from a local proxy; requires a loopback bind address |

Use `TRUST_CLOUDFLARE=1` only behind a local cloudflared connector. Do not trust forwarding headers from arbitrary clients.

An offline startup check (POSIX shell):

```sh
COLLECT_ENABLED=0 python3 server.py
```

This verifies startup, not live collection. Empty data is expected for a fresh offline database.

## Data and evidence

### Sources and storage

- **DexScreener:** public market metadata, including discovery through paid boost listings. Coverage is selective; inclusion is not an endorsement or smart-money classification.
- **Solana RPC:** supported finalized Pump bonding-curve `TradeEvent` observations. Collection is bounded, not comprehensive Solana indexing or full post-migration backfill.
- **SQLite:** retained market/trade observations and raw upstream receipts. Analytics read at most the latest 500 stored trades; this is an analysis window, not a promise of full history.

The decoder deliberately rejects transactions with failed inner calls or incomplete log stacks, even when the outer call reports success. Public RPC can throttle requests, omit unsupported versions or fail. Previously retained observations remain available and the UI reports source status.

### Interpretation

Wallet summaries describe the retained sample: buys, sells, tokens, available SOL totals and first/last observations. SOL totals are not profit, balances or cost basis. Missing amounts remain unknown.

The analytics relationship calculation examines at most 60 wallets ranked by retained buy count and returns at most 30 pairs with purchases overlapping across at least two distinct tokens. This is a bounded co-observation calculation, not an ownership or coordination inference. The hosted Network instead presents the direct token → buyers → wallet-records workflow; the repository frontend still has the older graph presentation.

The journal uses deterministic rules:

| Event | Meaning | Does not establish |
| --- | --- | --- |
| `FIRST_SEEN` | First verified trade for a token in the retained window | Token creation or first-ever trade |
| `CO_BUY` | Different event accounts bought the token in the sample | Distinct humans, shared owners or coordination |
| `SELL_OBSERVED` | A supported sell was recorded | Complete exit or realized profit |

Later-activity summaries count only strictly subsequent records for the same token within one hour. Missing later records do not prove inactivity. These summaries are not prediction evaluations.

There is no model inference API in the application runtime. Astra, Jev and other language models are not connected; adding a provider key alone does not integrate them. No validated profitability ranking, PnL, win rate, complete wallet history or automatic trading is implemented.

## Read-only API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Service health |
| `GET /api/snapshot` | Retained observations and source status |
| `GET /api/token?address=<mint>` | Inspect a token |
| `GET /api/wallet?address=<wallet>` | Inspect retained wallet activity |
| `GET /api/export` | JSON export |

User-supplied addresses must be valid base58-encoded 32-byte Solana addresses. The API does not accept arbitrary upstream URLs. Requests use timeouts, bounded upstream responses, caching and concurrency limits. The static server restricts access to data/source files and sets CSP headers. These safeguards do not constitute an independent security audit.

## Checks

Python checks do not require npm:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Node.js and npm are needed for frontend development tests only:

```sh
npm ci
node --test tests/*.test.mjs
```

With the local app running, install Playwright Chromium or use a system Chromium binary:

```sh
FRONTEND_URL=http://127.0.0.1:8787 CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node tests/frontend-browser.mjs
FRONTEND_URL=http://127.0.0.1:8787 CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node tests/e2e.mjs
```

Replace the executable path for your system. `e2e.mjs` defaults to system Chromium; `frontend-browser.mjs` can use a Playwright-installed browser when the override is omitted. Live-data E2E checks require successful collection; an empty or partial public source can prevent them passing. Unit fixtures are isolated in tests and are never production observations.

## Hosting and service boundaries

The public app is https://trenchnet.app. The Dockerfile prepares persistent-volume permissions and runs the application as an unprivileged user. Self-hosters must provide persistent storage for SQLite, TLS/reverse-proxy configuration and monitoring. Never commit database copies or credentials.

The Telegram bot is a **separate live service**, not part of the website's Docker entry point. See [the bot guide](telegram-bot.md) for its independent process and database. A running worker is not evidence that a genuine trade alert was delivered; delivery also depends on consent, cutoffs and a healthy fresh source.

`ops/budget_guard.py` is optional operator tooling for a separate scheduler, not application runtime. Its private configuration is not included in setup instructions. Provider billing can lag, and retained storage may remain billable after a service stops; it is not a provider-enforced hard spending cap.

Before a large public rollout: use a production HTTP server/reverse proxy, shared caching/rate limits, health monitoring, a dependable history source and observable full-history backfill. Future work includes better wallet-history coverage, cost-basis accounting when data supports it, and historical evaluation before any performance claims.
