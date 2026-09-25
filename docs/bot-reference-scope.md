# Notification scope and reference comparison

Reference: https://fomoradar.app/pro and /about. FOMO Radar describes multi-wallet burst/early-launch alerts, on-demand feeds, leaderboard lookup and a digest. TRENCHNET does not claim feature parity, paid token/burn subscriptions or a profitability ranking.

## Actual source contract

TRENCHNET uses the site's retained Pump bonding-curve transaction sample. Following an address filters this existing collection; it does not start complete tracking of that wallet. A followed account outside the collection can produce no notifications. The read-only recent feed must distinguish retained observations from newly delivered alerts and show event timestamps.

Trade alerts require a healthy fresh source, verified supported event data and an event newer than boot, subscription and follow cutoffs. A `partial` or stale source suppresses notifications; opening a menu or viewing old observations must not bypass those gates. An account in an event is not proof of a profitable human trader or complete exit.

No Jev, Astra, paid inference, wallet signatures, wallet connection or automatic trading. Other projects' Telegram credentials, workers and subscriber databases are not reused.

## Service boundaries and self-hosting

Public bot: https://t.me/trenchnetPF_bot. It is live as a separate worker, not part of the website container.

For your own instance, use the `ops/trenchnet-bot.service` template and provide your own dedicated token, source location and persistent SQLite path. Store credentials outside the repository with restrictive file permissions. Do not reuse another bot's token or subscriber database.

Before enabling a worker, verify bot identity, absence of a conflicting webhook and a single poller. Preserve preferences, cutoffs, delivery history and update offset during upgrades. Use SQLite's backup API for a running database; never start a second getUpdates poller merely to test an existing bot.

Keep source availability, process health, Telegram message acceptance and genuine trade-alert delivery as separate evidence levels. Website hosting and the worker are separate services; a source outage or partial coverage is not fixed by adding Telegram buttons.

## Remaining product work

Grouped-buy burst notifications, trader-quality evaluation, complete arbitrary-wallet tracking and daily digests are separate features, not part of the wallet-follow/menu release. Do not describe stored recent trades as live signals or replay them on subscription/restart.
