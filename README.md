# TRENCHNET

Работающий read-only прототип исследовательского терминала Solana/Pump для Logics.

## Что работает

- Radar: публичная рыночная информация DexScreener, фильтры сделок/покупок/продаж, поиск по адресу, watchlist в браузере.
- Traders: краткое описание наблюдаемого поведения, покупки/продажи, суммы SOL и первое/последнее событие в выборке, ссылки на транзакции. Суммы SOL не являются PnL.
- Network: граф аккаунт ↔ токен; повторные пересечения покупок минимум по двум разным токенам, с переходами к кошелькам и evidence. Анализ ограничен 60 аккаунтами с наибольшим числом наблюдаемых покупок, выводятся до 30 пар.
- Journal: воспроизводимые FIRST_SEEN / CO_BUY / SELL_OBSERVED и строго последующие события того же токена в пределах часа. Отсутствие дальнейших записей не означает отсутствие активности. Все расчёты по последним максимум 500 сохранённым сделкам.
- Token/wallet drawers, Solscan links, JSON export, mobile layout.
- SQLite, raw upstream receipts, bounded periodic collection. Application runtime uses only Python standard library.

## Важные ограничения

Это **не готовая система прибыльного автотрейдинга**. Нет подключения кошелька, приватных ключей, подписания или исполнения сделок.
Astra и Jev **не подключены**; журнал использует детерминированные правила, не языковую модель.
История ограничена выборкой; PnL, win rate, остатки, полные выходы, точный рейтинг и связность владельцев не вычисляются.
Совместная покупка токена не доказывает сговор или разные человеческие личности.
Метаданные рынка обнаруживаются в том числе через список оплаченных boosts DexScreener. Это не сигналы умных денег.
Коллектор поддерживает Pump bonding-curve TradeEvent, не все маршруты Solana и не полный post-migration backfill.
Декодер намеренно отклоняет транзакции с неуспешными внутренними вызовами или неполным стеком логов, даже когда внешний вызов завершился успешно.
Public RPC может ограничивать запросы, пропускать неподдерживаемые версии или перестать отвечать. UI сохраняет предыдущую выборку и показывает состояние источника.

## Запуск

Требуется Python 3.11+; runtime без pip/npm.

```bash
python3 server.py
```

Открыть http://127.0.0.1:8787. Коллектор стартует в фоне и повторяет цикл примерно каждые 90 секунд плюс время запроса.

Переменные окружения:
- `HOST` (default `127.0.0.1`; Docker sets `0.0.0.0`), `PORT` (default `8787`)
- `DB_PATH` (default `./data/trenchnet.sqlite`)
- `COLLECT_INTERVAL` (default `90`, минимум `90`)
- `COLLECT_ENABLED=0` отключает фоновые сетевые обращения
- `TRUST_CLOUDFLARE=1` trusts Cloudflare client-IP headers only from a local proxy and requires loopback HOST; use only behind a local cloudflared connector

Сначала появится пустое состояние. Реальные данные появятся только после успешного обращения к публичным источникам. В архиве нет фиктивных рыночных данных, приватных ключей или live SQLite.

## Проверки

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
npm ci
node --test tests/*.test.mjs
FRONTEND_URL=http://127.0.0.1:8787 CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node tests/frontend-browser.mjs
FRONTEND_URL=http://127.0.0.1:8787 CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node tests/e2e.mjs
```

Browser E2E checks require a running app and successful live collection. No mocked network rows are inserted into the app for browser checks. Unit fixtures are isolated in tests and never loaded into production.
`e2e.mjs` uses system Chromium by default. Set `CHROMIUM_EXECUTABLE_PATH` to an installed Chromium binary. For `frontend-browser.mjs`, omit the variable if Playwright browsers are installed via `npx playwright install chromium`.

## Публикация

Публичный адрес: **https://trenchnet.app**. Сервис размещён в Railway, данные находятся на persistent volume `/app/data`, DNS у Name.com. Dockerfile подготавливает права тома и запускает приложение от непривилегированного пользователя.

Локальный `ops/budget_guard.py` предназначен для отдельного планировщика, а не контейнера приложения. Он читает приватный `data/hosting-budget.json`, проверяет расходы только указанного проекта и останавливает только указанный сервис при расходе $3.50, недоступном биллинге или окончании согласованного срока. Применённый срок запуска: до 25 сентября 2026, 02:50 UTC. Проверка каждые 15 минут. Это **не жёсткий лимит провайдера**: биллинг запаздывает; сохранённый том может тарифицироваться после остановки. База и код не удаляются.

Inference API в приложении отсутствует. Наличие ключа AI Gateway не включает запросы к моделям.
Перед публичным массовым запуском нужны production HTTP server/reverse proxy, shared cache/rate limits, health monitoring, стабильный источник истории и наблюдаемый full-history backfill.

## API

- `GET /api/health`
- `GET /api/snapshot`
- `GET /api/token?address=<mint>`
- `GET /api/wallet?address=<wallet>`
- `GET /api/export`

Все API read-only; пользовательские адреса проходят проверку base58/32-byte. Внешние URL не принимаются. Есть ограничение ответа upstream, таймауты, bounded cache/concurrency, заголовки CSP и запрет доступа к data/source-файлам через static server.

## Telegram-уведомления

Отдельный read-only worker: `telegram_bot.py`. Статус: реализация и локальные проверки; **не подключён к Telegram и не запущен** без отдельного токена TRENCHNET. Документация: [docs/telegram-bot.md](docs/telegram-bot.md). Сравнение с референсом и границы: [docs/bot-reference-scope.md](docs/bot-reference-scope.md).

`ops/trenchnet-bot.service` — проверенный systemd-шаблон, не активированный сервис. Он не включает бота в существующий Docker-образ и не продлевает срок хостинга сайта.

## Следующие интеграции

1. Более полная история отслеживаемых кошельков и учёт себестоимости при достаточных данных.
2. Историческая оценка сигналов до любых claims о доходности.

Настройка Jev отложена пользователем; Astra и другие платные модели не входят в текущий релиз.

Деньги пользователей приложение не принимает и не перемещает.
