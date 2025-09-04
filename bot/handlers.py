from __future__ import annotations
import json, random, re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .config import ADMIN_USERNAMES, NETWORKS, DEFAULT_MIN_AMOUNT
from .db import db, upsert_state, get_state
from .market import get_dexscreener_info, get_coingecko_info
from .blockchain import is_token_holder
from .config import BOT_USERNAME


def is_admin(update: Update) -> bool:
    u = update.effective_user
    return (u and u.username and u.username in ADMIN_USERNAMES)


def start_text_for_user() -> str:
    return (
        "Welcome! Verify you're human and a token holder to get the private group link.\n\n"
        "Tap **Verify** to begin."
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args  # will contain ["verify"] if user clicked deep link

    # Case 1: Deep link from channel -> go straight to verify intro
    if args and args[0] == "verify":
        kb = [[InlineKeyboardButton("Verify", callback_data="user_verify")]]
        await update.message.reply_text(
            start_text_for_user(),
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # Case 2: Admins get config panel
    if is_admin(update):
        kb = [[InlineKeyboardButton("Configure Project", callback_data="admin_config")]]
        await update.message.reply_text(
            f"Hello @{update.effective_user.username}! You're authorized.\nChoose an option:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # Case 3: Normal user flow
    kb = [[InlineKeyboardButton("Verify", callback_data="user_verify")]]
    await update.message.reply_text(
        start_text_for_user(),
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def send_channel_pin(context):
    with db() as con:
        cur = con.cursor()
        # get the latest project (or you can filter by admin/owner if needed)
        cur.execute("SELECT id, channel_chat_id FROM projects ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()

    if not row:
        return  # no project configured yet
    project_id, channel_id = row

    # Build button
    keyboard = [
        [InlineKeyboardButton("✅ Verify Now", url=f"https://t.me/{BOT_USERNAME}?start=verify")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Post in the project’s channel
    msg = await context.bot.send_message(
        chat_id=channel_id,
        text=(
            "🚀 Welcome!\n\n"
            "🔒 Holders-only group requires verification.\n\n"
            "Click below to verify:"
        ),
        reply_markup=reply_markup
    )

    # Pin it
    await context.bot.pin_chat_message(
        chat_id=channel_id,
        message_id=msg.message_id,
        disable_notification=True
    )

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Only authorized admins can use this command.")
        return
    kb = [[InlineKeyboardButton("Configure Project", callback_data="admin_config")]]
    await update.message.reply_text("Admin panel:", reply_markup=InlineKeyboardMarkup(kb))


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "admin_config":
        rows = []
        row = []
        for key, name in NETWORKS.items():
            row.append(InlineKeyboardButton(name, callback_data=f"net:{key}"))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        await q.edit_message_text("Select network:", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("net:"):
        net = data.split(":", 1)[1]
        upsert_state(q.from_user.id, "SET_CONTRACT", json.dumps({"network": net}))
        await q.edit_message_text(f"Selected **{NETWORKS.get(net, net)}**.\n\nSend the *contract address/mint* as a message.")
        return

    if data == "user_verify":
        a = random.randint(2, 9)
        b = random.randint(2, 9)
        answer = a + b
        upsert_state(q.from_user.id, "VERIFY_MATH", json.dumps({"answer": answer}))
        await q.edit_message_text(f"Human check: What is {a} + {b}?")
        return


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    uid = update.effective_user.id
    state, payload = get_state(uid)

    if state == "SET_CONTRACT":
        data = json.loads(payload or "{}")
        data["contract"] = text
        upsert_state(uid, "SET_GROUP_LINK", json.dumps(data))

        dex = get_dexscreener_info(text) or {}
        platform_map = {"eth": "ethereum", "bsc": "binance-smart-chain", "base": "base", "sol": "solana"}
        cg_platform = platform_map.get(data["network"])
        cg = get_coingecko_info(cg_platform, text) if cg_platform else {}

        info_lines = ["Got contract."]
        if dex:
            info_lines.append(f"• Dexscreener: {dex.get('symbol') or ''} {dex.get('priceUsd') or ''} FDV: {dex.get('fdv') or ''}")
        if cg:
            info_lines.append(f"• CoinGecko: ${cg.get('priceUsd')} MC: {cg.get('marketCap')}")

        await update.message.reply_text("\n".join(info_lines) + "\n\nSend the *private group invite link* (the link we should give verified holders).")
        return
    if state == "SET_GROUP_LINK":
        data = json.loads(payload or "{}")
        group_link = text
        data["group_link"] = group_link
        upsert_state(uid, "SET_CHANNEL", json.dumps(data))
        await update.message.reply_text(
            "Got the group link.\n\nNow send the *channel username* (e.g. @MyChannel) "
            "or channel chat_id (e.g. -100123456789) where the Verify button should be posted."
        )
        return

    if state == "SET_CHANNEL":
        data = json.loads(payload or "{}")
        channel_id = text.strip()
        with db() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO projects
                (owner_username, network, contract_address, group_invite_link, channel_chat_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    update.effective_user.username or "",
                    data.get("network"),
                    data.get("contract"),
                    data.get("group_link"),
                    channel_id,
                ),
            )
        upsert_state(uid, None, None)
        await update.message.reply_text("✅ Project saved. Pin message will be sent to your channel shortly.")

        # trigger posting
        try:
            await send_channel_pin(context)
        except Exception as e:
            await update.message.reply_text(f"⚠️ Could not post in channel: {e}")
        return


    if state == "VERIFY_MATH":
        data = json.loads(payload or "{}")
        try:
            if int(text) == int(data.get("answer")):
                upsert_state(uid, "VERIFY_WALLET", "{}")
                await update.message.reply_text("✅ Human check passed.\nNow send your **wallet address**:")
            else:
                await update.message.reply_text("❌ Wrong. Tap Verify again.")
                upsert_state(uid, None, None)
        except Exception:
            await update.message.reply_text("Please reply with a number.")
        return

    if state == "VERIFY_WALLET":
        wallet = text
        with db() as con:
            cur = con.cursor()
            cur.execute("SELECT id, network, contract_address, group_invite_link FROM projects ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
        if not row:
            await update.message.reply_text("No project configured yet. Please try later.")
            upsert_state(uid, None, None)
            return
        project_id, network, contract, group_link = row
        if network in ("eth", "base", "bsc") and not re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet):
            await update.message.reply_text("That doesn't look like a valid EVM address. Try again:")
            return

        holder = is_token_holder(network, wallet, contract, DEFAULT_MIN_AMOUNT)
        if holder:
            with db() as con:
                cur = con.cursor()
                cur.execute(
                    "INSERT INTO users (telegram_id, username, project_id, verified, wallet_address) VALUES (?, ?, ?, ?, ?)",
                    (update.effective_user.id, update.effective_user.username or "", project_id, 1, wallet)
                )
            await update.message.reply_text(f"✅ Verified holder.\nHere is your private group link:\n{group_link}")
        else:
            await update.message.reply_text("❌ You don't appear to hold the token. If you think this is wrong, try again later.")
        upsert_state(uid, None, None)
        return

    if is_admin(update):
        await update.message.reply_text("You're an admin. Use /admin to configure a project.")
    else:
        await update.message.reply_text("Tap **Verify** to begin.")
