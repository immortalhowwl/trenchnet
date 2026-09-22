# Notification scope and reference comparison

Reference checked directly: https://fomoradar.app/pro and /about. Fomo Radar advertises multi-wallet burst and early-launch alerts, on-demand /hot /signals /fresh /exits, leaderboard lookup and daily digest. Its paid token/burn subscription mechanism and trader rating are not part of this implementation.

TRENCHNET first bot release sends observed purchases/sales for explicitly followed Solana wallets from the existing saved snapshot. It does not backfill or independently monitor a wallet merely because someone follows it. The underlying collector is a bounded Pump bonding-curve sample, not complete Solana coverage, a ranked cohort, or an instant feed. A follow may produce no notifications when that wallet is outside collection. Never market this as guaranteed tracking of arbitrary wallets.

No Jev, Astra or paid inference. No payments, signatures, wallet connection or automatic trades. No other project's Telegram credentials or subscriber databases are reused.

## Deployment gate

A dedicated BotFather token is required before activation. Keep TRENCHNET_BOT_TOKEN in a root-owned 0600 /etc/trenchnet-bot.env file, never in Git, command arguments, or logs. The prepared ops/trenchnet-bot.service is a template, NOT an installed or enabled service. Its code installation path is /opt/trenchnet-bot, its independent StateDirectory is /var/lib/trenchnet-bot. Verify getMe matches the intended username and getWebhookInfo shows no conflicting webhook before starting one poller. Do not clear a webhook or reuse an existing token without confirmed ownership and explicit intent.

Website hosting remains the separately agreed time-limited run. Bot delivery depends on that site being available; the service template does not extend the hosting period or budget. An unavailable/stale snapshot must not send replayed or fabricated events.

Later: consented grouped-buy alerts from verified fresh events, simple read-only feed commands, improved collector coverage, and honest trader-history evaluation. These are not complete in the initial wallet-follow bot.
