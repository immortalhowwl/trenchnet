# Notification scope and reference comparison

Reference: https://fomoradar.app/pro and /about. FOMO Radar describes multi-wallet burst/early-launch alerts, on-demand feeds, leaderboard lookup and a digest. TRENCHNET does not claim feature parity, paid token/burn subscriptions or a profitability ranking.

## Actual source contract

TRENCHNET uses the site's retained Pump bonding-curve transaction sample. Following an address filters this existing collection; it does not start complete tracking of that wallet. A followed account outside the collection can produce no notifications. The read-only recent feed must distinguish retained observations from newly delivered alerts and show event timestamps.

Trade alerts require a healthy fresh source, verified supported event data and an event newer than boot, subscription and follow cutoffs. A `partial` or stale source suppresses notifications; opening a menu or viewing old observations must not bypass those gates. An account in an event is not proof of a profitable human trader or complete exit.

No Jev, Astra, paid inference, wallet signatures, wallet connection or automatic trading. Other projects' Telegram credentials, workers and subscriber databases are not reused.

## Established deployment

Dedicated bot: https://t.me/trenchnetPF_bot

- Existing systemd service: `trenchnet-bot.service`.
- Installed source: `/opt/trenchnet-bot/telegram_bot.py`.
- Root-owned credential: `/etc/trenchnet-bot.env`, mode 0600; never publish or print.
- Persistent SQLite: `/var/lib/trenchnet-bot/notifications.sqlite`.
- Independent source API: `https://trenchnet.app/api/snapshot`.

Before upgrades, verify bot identity, no webhook conflict and a single poller. Back up SQLite with its backup API, preserve preferences/cutoffs/delivery history/update offset, then restart only this dedicated worker. Never create a second getUpdates poller for a smoke test. Keep source deployment, process health, Telegram message acceptance and genuine trade-alert delivery as separate evidence levels.

Website hosting and the worker are separate services. Source outages or partial coverage are not cured by adding Telegram buttons. No new paid provider or hosting plan is provisioned by this bot UI update.

## Remaining product work

Grouped-buy burst notifications, trader-quality evaluation, complete arbitrary-wallet tracking and daily digests are separate features, not part of the wallet-follow/menu release. Do not describe stored recent trades as live signals or replay them on subscription/restart.
