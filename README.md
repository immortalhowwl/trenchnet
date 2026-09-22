# TRENCHNET

Работающий read-only прототип исследовательского терминала Solana/Pump для Logics.

## Что работает

- Radar: публичная рыночная информация DexScreener, фильтры сделок/покупок/продаж, поиск по адресу, watchlist в браузере.
- Traders: наблюдаемые аккаунты, количество покупок/продаж в сохранённой выборке, реальные транзакции.
- Network: граф аккаунт ↔ токен с переходом в подробности.
- Journal: воспроизводимые FIRST_SEEN / CO_BUY / SELL_OBSERVED с ссылками на подтверждающие сделки.
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

Первый просмотр: временный Cloudflare Quick Tunnel. Это **не production-хостинг**, не постоянный адрес и не привязка домена. Срок не гарантирован: работает пока живы процессы сервера и туннеля; при рестарте адрес меняется.
`trenchnet.app` не подключён. Новый платный hosting/API не оформлялся.

Для постоянного запуска подготовлен Dockerfile (образ в этой сессии не собирался). На Railway требуется новый сервис, согласование расходов и persistent volume `/app/data`; затем подключение домена и DNS у Name.com. Не использовать эфемерный диск для сохраняемой истории.
Перед публичным массовым запуском нужны production HTTP server/reverse proxy, shared cache/rate limits, health monitoring, стабильный источник истории и наблюдаемый full-history backfill.

## API

- `GET /api/health`
- `GET /api/snapshot`
- `GET /api/token?address=<mint>`
- `GET /api/wallet?address=<wallet>`
- `GET /api/export`

Все API read-only; пользовательские адреса проходят проверку base58/32-byte. Внешние URL не принимаются. Есть ограничение ответа upstream, таймауты, bounded cache/concurrency, заголовки CSP и запрет доступа к data/source-файлам через static server.

## Следующие интеграции

1. Постоянный hosting и DNS `trenchnet.app`.
2. Выбор отслеживаемых кошельков + полный backfill и учёт себестоимости.
3. Подключение реального Astra/Jev по согласованному API/бюджету с журналом входов/выходов, а не подмена правил AI.
4. Историческая оценка сигналов до любых claims о доходности.

Деньги пользователей приложение не принимает и не перемещает.
