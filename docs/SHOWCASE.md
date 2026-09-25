# Visual tour

[← TRENCHNET](../README.md)

## Capture provenance

These are direct screenshots of **https://trenchnet.app**, captured on **2026-09-25 during the 04:00 UTC hour**, using Playwright with system Chromium and a 1440 × 1000 viewport. No fixture data, mocked responses, rewritten labels or synthetic metrics were inserted. The interface reported **partial collection**, and its warning is visible in every capture. Data changes over time; these images are dated observations, not a current service-status guarantee.

The cover is a new composition using TRENCHNET's existing original helmeted mascot artwork, black and white typography, and cyan `#5debff`. It is branding, not a transaction graph or evidence of model integration. No reference-project artwork is reused.

## Hosted app and repository scope

This is a documentation-and-media update. The hosted app has newer branding, route navigation and a token → observed buyers → selected wallet's recorded trades Network view. Those application changes are not included in this commit. The repository frontend still contains the earlier presentation and network graph. Cloning the repository runs that source version, not an exact reproduction of the screenshots.

The bot is independently deployed and active. Its deployed welcome branding can also differ from the checked-in worker; the command, consent and source-quality rules are documented separately in the [Telegram guide](telegram-bot.md).

## Radar

Route: [/#/radar/fresh](https://trenchnet.app/#/radar/fresh)

The Fresh tab shows recorded buys, available SOL amounts and transaction links. It is not a newly launched-token list. The market and trade counters describe this retained snapshot, not universal chain coverage.

![Radar — observed buys](media/radar.png)

## Traders

Route: [/#/traders](https://trenchnet.app/#/traders)

Wallet activity counts and sample summaries. This is not a leaderboard of profitable traders. The wide table can be scrolled horizontally in the app; this capture shows its initial position.

![Traders — observed wallet activity](media/traders.png)

## Network

Route: [/#/network](https://trenchnet.app/#/network)

Choose a token with recorded activity, select an observed buyer and inspect that wallet's available records. The right-hand side can include other tokens in the current snapshot. It is not complete wallet history or an ownership map.

![Network — token, buyers and recorded trades](media/network.png)

## Journal

Route: [/#/journal](https://trenchnet.app/#/journal)

Rule-derived events keep receipt links beside their interpretation and later-activity window. Pending means no later records in the retained sample, not proof of no on-chain activity.

![Journal — rules and receipts](media/journal.png)
