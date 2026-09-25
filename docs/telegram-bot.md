# TRENCHNET Telegram wallet alerts

The dedicated [@trenchnetPF_bot](https://t.me/trenchnetPF_bot) is live as an independent service (process status checked 2026-09-25). The website and worker are deployed separately. Process health does not establish genuine trade-alert delivery: consent, freshness and source-quality gates still apply. Partial snapshots intentionally suppress the feed and alerts.

## Commands and consent

| Command | Effect |
|---|---|
| `/start`, `/help` | Explain limited Pump sample. New chats OFF, existing preferences unchanged. |
| `/follow ADDRESS` | Add case-sensitive 32-byte Solana address; maximum 10 per chat. Does not extend collector coverage. |
| `/unfollow ADDRESS` | Remove only that wallet. |
| `/subscribe` | Explicitly enable alerts. Repeating while active preserves cutoff. |
| `/stop` | Persist OFF before attempting acknowledgement. Retain follows. |
| `/status` | Show alert state, followed wallets, source update timestamp, collector state and freshness. |
| `/wallets` | List up to 10 followed addresses with the management menu. |
| `/feed` | Read-only latest eligible observed trades (up to 5) across all sampled wallets. |
| `/follow`, `/unfollow` without address | Start guided address input, persisted across restart. Invalid input can be retried. |
| `/cancel` | Cancel pending input without changing alert preferences. |

English inline controls: **Add wallet**, **My wallets**, **Remove wallet**, **Enable alerts**, **Pause alerts**, **Recent trades**, **Status**, **Help**, **Cancel**, plus website/transaction links. Add/remove asks for the full case-sensitive Solana address; My wallets shows addresses to copy. Any new command or menu action replaces/cancels pending input.

Start/help, adding/removing wallets and viewing the feed never implicitly enable alerts. Enable/Pause are explicit actions; repeated Enable retains the active subscription cutoff. Enabling with an empty list remains command-compatible, but no alerts can arrive until a wallet is followed. Adding a wallet to an already enabled subscription retains ON and starts that wallet’s cutoff now.

Only private-chat text messages and private callbacks where `callback_query.from.id == message.chat.id` are processed. No groups, channels, inline-mode or edited messages. Unknown/foreign callbacks cannot mutate preferences or fetch the feed. Callback queries are acknowledged through `answerCallbackQuery`, including ignored callbacks when an ID is available; failures do not prevent local command processing. Messages use plain text, not interpolated HTML. The bot does not claim profitability, ownership identity, complete exits or a ranked trader cohort.

## Local checks

Python 3.11+, standard library, Linux flock. No pip dependencies.

```sh
python3 -m unittest discover -s tests -v
python3 telegram_bot.py --help
python3 telegram_bot.py --smoke
```

`--help` performs no network calls. `--smoke` makes one bounded GET to https://trenchnet.app/api/snapshot and normalizes real data; it NEVER contacts Telegram. Zero eligible trades is a legitimate result, including when source status is partial. It is not evidence of zero on-chain activity.

## Runtime and persistence

Entrypoint: `python3 telegram_bot.py`.

- Required environment: `TRENCHNET_BOT_TOKEN` (dedicated bot, never another app's token).
- Optional `BOT_DB_PATH`, default `data/telegram-bot.sqlite` beside source.
- Separate SQLite persists recipient state, follows/cutoffs, Telegram update offset, `(chat,event)` delivery records and pending guided input in the additive `inputs` table. Existing tables/recipient rows are not rebuilt or reset. Do not reuse website DB or other bots' subscriber DBs.
- A database-path flock prevents two local workers sharing this state. It does not prevent a second host polling the same token.
- Dedicated `ops/trenchnet-bot.service` is the service template; its presence in source does not establish deployed status. See `bot-reference-scope.md` for installation paths and ownership/webhook checks.
- Token goes in secret storage, e.g. root-owned 0600 `/etc/trenchnet-bot.env`. Never paste into source, CLI arguments, Git, or logs. No example credential included.
- Before enablement verify getMe identity and absence of conflicting webhook/poller. The worker itself does not delete webhooks or change other bots.
- Outbound hosts: trenchnet.app and api.telegram.org. Requests reject redirects, use 30-second timeout and 2 MB response cap. Fixed Solscan transaction links are constructed only from validated signatures.

## Read-only feed and source status

`Bot.updates(..., snapshot=transport.snapshot, answer=transport.answer)` injects real source and callback transports; tests use offline fixtures. Feed/status source calls do not alter subscription/follow cutoffs or mark events delivered. Feed is not restricted to followed wallets and is not a historical wallet explorer. It displays validated side, wallet, mint, observed timestamp and a validated Solscan transaction URL; no invented price, amount, return, PnL or ranking.

Freshness is based on the source `updatedAt`, not request time. The status view discloses stale/invalid timestamps, partial/error/starting/unknown collector states and unavailable source. The feed uses the alert validator (10-minute source/event window, collector `ok`) and suppresses records for stale or partial snapshots. An empty eligible sample is explicitly not proof of no on-chain activity. At most five latest eligible trades are shown.

## Delivery semantics

Eligibility: verified finalized Pump event with valid addresses/signature/canonical ID, both snapshot and event at most 10 minutes old, no future timestamp, collector status `ok`. Partial/error snapshots are deliberately suppressed, even when they contain some valid records. Events must be strictly later than process boot, subscription and that wallet's follow cutoff. Restart downtime is NOT replayed.

Telegram polling uses up to 100 updates with 20-second long poll. Pending commands are processed before alerts; a full update batch or failed poll prevents alerts that iteration. Maximum 20 delivery attempts per snapshot pass, paced sends. Only a successful Telegram response marks delivered. 429 retry_after becomes a cooldown, not an unbounded sleep; source fetches are independent. A failed acknowledgement is not retried, but command state and offset remain committed. Failed alert sends stay eligible while fresh. This is not exactly-once: a timeout or crash after remote acceptance can cause duplication. Restart/expiry can lose unsent events.

No server-side retention cleanup for subscriber state is implemented. Back up the bot SQLite independently using SQLite backup while live, or stop worker before copying the DB and associated journal files. Preserve state on upgrades.

## Limits / not yet implemented

No grouped-buy burst alerts, digest, trader ranking, paid subscription or automatic trading. `/follow` filters what the existing collector retained; it does NOT initiate comprehensive collection of an arbitrary wallet. Bounded attempt counts and synchronous I/O make this an initial low-volume worker, not a proven large-audience broadcaster. A chronically failing set of recipients can delay other recipients; operational monitoring and fair retry queues are a later scaling gate.

Website and bot availability are independent. Without a healthy, fresh site snapshot there are no eligible alerts.
