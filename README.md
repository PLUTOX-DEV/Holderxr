# Telegram Token Holder Verification Bot

A **Telegram bot** for gating communities by verifying that users are *human* and *holders* of a token.
It supports multi-chain (EVM, Solana, Sui) with API hooks for **Dexscreener**, **CoinGecko**, and placeholders for **PumpFun**.

> **Note on Telegram constraints**
> - Bots cannot DM users first. Users must click **Start**.
> - Channels do not expose all subscribers to bots. Gate access by posting a button that opens the bot (deep-link) or by using join-request approval in groups.
> - This template uses polling for simplicity. For production, consider webhooks.

---

## Features

- Whitelisted **admin usernames** can configure projects (restrict resale/usage).
- Admin flow: choose network → enter token contract/mint → (optional) preview market info (Dexscreener/CoinGecko) → save group invite link.
- User flow: simple math captcha → wallet address → on-chain holder check → if true, receive group invite link.
- SQLite for state: `projects`, `users`, `states`.

---

## Quick Start

```bash
python -m venv .venv
# Windows
# .venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in:
# TELEGRAM_BOT_TOKEN=...
# ADMIN_USERNAMES=p-lutox,user2,user3,user4
# Optionally add API keys for explorers/providers

python main.py
```

**Telegram setup tips**
- Add the bot to your channel or group if you want moderation features.
- Post a pinned message: *"Click @YourBot to verify & get the private group link."*
- Use `/admin` to configure the active project.

---

## Config / Env

See `.env.example`. Supported variables:

- `TELEGRAM_BOT_TOKEN` (required)
- `ADMIN_USERNAMES` (comma-separated, no `@`)
- Optional API keys:
  - `ETHERSCAN_API_KEY`, `BASESCAN_API_KEY`, `BSCSCAN_API_KEY`
  - `ALCHEMY_API_KEY`
  - `HELIUS_API_KEY` (Solana)
  - `SUI_RPC_URL` (defaults to mainnet public URL)

---

## Structure

```
telegram-token-verifier-bot/
├─ main.py
├─ requirements.txt
├─ README.md
├─ .env.example
└─ bot/
   ├─ __init__.py
   ├─ config.py
   ├─ db.py
   ├─ market.py
   ├─ blockchain.py
   └─ handlers.py
```

---

## Roadmap / TODO

- Add decimals-aware ERC‑20/SPL/Sui balance checks (currently uses non-decimal or explorer balances).
- Add webhook mode + persistence.
- Add per-channel project mapping (now uses the latest project as active for simplicity).
- Add PumpFun-specific tracking endpoints.
- Improve validations for wallet formats per chain.
- Add anti-spam/rate-limiting.
- Add admin UI commands to list/delete projects.
