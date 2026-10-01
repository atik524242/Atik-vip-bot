# AR OTP Telegram Bot

Telegram bot for OTP stock, buy-service orders, deposits, withdrawals, and
admin notifications.

## Start

The worker runs with:

```bash
python -u bot.py
```

The bot needs the secret environment variable `TELEGRAM_BOT_TOKEN`. Never put
the token in this file, in source code, or in a ZIP file. Optional Firebase
variables enable durable state across restarts:

- `FIREBASE_SERVICE_ACCOUNT_JSON`
- `FIREBASE_SERVICE_ACCOUNT_BASE64`
- `FIREBASE_CREDENTIALS_PATH`
- `FIREBASE_PROJECT_ID`
- `FIREBASE_COLLECTION`

Without Firebase, the JSON files in the project directory are used as the
local persistence layer.

## Super admin

The only configured super admin is:

```text
6664150885
```

Other users may be added as time-limited admins from the admin panel, but they
do not become super admins and cannot use super-admin-only actions.

## Important files

- `bot.py` — Telegram handlers, background monitors, orders, deposits, and
  admin panel
- `buy_service_settings.json` — VPN/proxy products, prices, payment details,
  and exchange rate
- `group_settings.json` — OTP groups and bot settings
- `users.json` — registered Telegram user IDs
- `deposit_requests.json` — deposit requests and approval status
- `deposit_balances.json` — approved deposit balances
- `balances.json` — OTP reward balances
- `firebase_store.py` — optional Firestore mirror for JSON state

## Buy-service flow

1. The user selects VPN or proxy and sends a payment screenshot.
2. The order is saved to `buy_orders_log.json`.
3. The super admin receives the screenshot and delivery action.
4. VPN credentials or proxy details are collected only in memory.
5. The user receives the delivery message.
6. The order is marked complete only after delivery succeeds.

If Telegram cannot deliver the user message, the order remains pending and the
admin receives a delivery-failed notice instead of a false success message.

## Deposit flow

Deposit requests are saved before any notification is attempted. The admin
notification has retry handling, so a temporary Telegram failure does not lose
the request. Approve or reject buttons update the request and notify the user.

## Broadcast flow

Broadcast supports text, photos, videos, GIFs, stickers, audio, voice,
documents, and video notes. It sends in a background worker, retries ordinary
HTML formatting failures as plain content, and sends a final report with:

- Success count
- Failed count
- Total recipient count

Paid WhatsApp imports also send the normal `NEW NUMBERS` notification. The
United States flag is permanently configured with custom emoji ID
`5294244076533600593` and is used in number notifications and assignment
messages.

## Troubleshooting

Check the Telegram Bot Worker log first. A missing `TELEGRAM_BOT_TOKEN` means
the secret is not available to the worker environment; add or re-save it in
the platform's secure Secrets section, then restart the worker.

For delivery issues, check:

1. The bot token is valid and the bot is not running in another polling
   process.
2. `6664150885` has opened the bot chat at least once.
3. The bot has permission to send messages in configured groups.
4. `deposit_requests.json` and `buy_orders_log.json` contain the request.