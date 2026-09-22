# TRENCHNET Telegram wallet alerts

Status: code tested locally, not registered/connected/deployed to Telegram. Dedicated BotFather token is missing. No live Telegram messages have been sent.

## Commands and consent

| Command | Effect |
|---|---|
| `/start`, `/help` | Explain limited Pump sample. New chats OFF, existing preferences unchanged. |
| `/follow ADDRESS` | Add case-sensitive 32-byte Solana address; maximum 10 per chat. Does not extend collector coverage. |
| `/unfollow ADDRESS` | Remove only that wallet. |
| `/subscribe` | Explicitly enable alerts. Repeating while active preserves cutoff. |
| `/stop` | Persist OFF before attempting acknowledgement. Retain follows. |
| `/status` | Show state and followed wallets. |

Only private-chat text messages are processed. No groups, channels or edited messages. Website and transaction buttons are English. Messages use plain text, not interpolated HTML. The bot does not claim profitability, ownership identity, complete exits or a ranked trader cohort.

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
- Separate SQLite persists recipient state, follows/cutoffs, Telegram update offset and `(chat,event)` delivery records. Do not reuse website DB or other bots' subscriber DBs.
- A database-path flock prevents two local workers sharing this state. It does not prevent a second host polling the same token.
- Dedicated `ops/trenchnet-bot.service` is an UNINSTALLED template. See `bot-reference-scope.md` for installation paths and ownership/webhook checks.
- Token goes in secret storage, e.g. root-owned 0600 `/etc/trenchnet-bot.env`. Never paste into source, CLI arguments, Git, or logs. No example credential included.
- Before enablement verify getMe identity and absence of conflicting webhook/poller. The worker itself does not delete webhooks or change other bots.
- Outbound hosts: trenchnet.app and api.telegram.org. Requests reject redirects, use 30-second timeout and 2 MB response cap. Fixed Solscan transaction links are constructed only from validated signatures.

## Delivery semantics

Eligibility: verified finalized Pump event with valid addresses/signature/canonical ID, both snapshot and event at most 10 minutes old, no future timestamp, collector status `ok`. Partial/error snapshots are deliberately suppressed, even when they contain some valid records. Events must be strictly later than process boot, subscription and that wallet's follow cutoff. Restart downtime is NOT replayed.

Telegram polling uses up to 100 updates with 20-second long poll. Pending commands are processed before alerts; a full update batch or failed poll prevents alerts that iteration. Maximum 20 delivery attempts per snapshot pass, paced sends. Only a successful Telegram response marks delivered. 429 retry_after becomes a cooldown, not an unbounded sleep; source fetches are independent. A failed acknowledgement is not retried, but command state and offset remain committed. Failed alert sends stay eligible while fresh. This is not exactly-once: a timeout or crash after remote acceptance can cause duplication. Restart/expiry can lose unsent events.

No server-side retention cleanup for subscriber state is implemented. Back up the bot SQLite independently using SQLite backup while live, or stop worker before copying the DB and associated journal files. Preserve state on upgrades.

## Limits / not yet implemented

No grouped-buy burst alerts, digest, trader ranking, paid subscription, on-demand feed commands or automatic trading. `/follow` filters what the existing collector retained; it does NOT initiate comprehensive collection of an arbitrary wallet. Bounded attempt counts and synchronous I/O make this an initial low-volume worker, not a proven large-audience broadcaster. A chronically failing set of recipients can delay other recipients; operational monitoring and fair retry queues are a later scaling gate.

Website hosting has its own agreed expiry and budget; running this bot does not extend them. Without a healthy site snapshot there are no alerts.
