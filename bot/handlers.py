# handlers.py
from __future__ import annotations
import json
import random
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .config import ADMIN_USERNAMES, NETWORKS, DEFAULT_MIN_AMOUNT, BOT_USERNAME
from .db import db, upsert_state, get_state, get_latest_project, save_verified_user
from .market import get_dexscreener_info, get_coingecko_info
from .blockchain import is_token_holder

logger = logging.getLogger(__name__)


def is_admin(update: Update) -> bool:
    u = update.effective_user
    return (u and u.username and u.username in ADMIN_USERNAMES)


def start_text_for_user() -> str:
    return (
        "Welcome! Verify you're human and a token holder to get access to the private group.\n\n"
        "Tap **Verify** to begin."
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if args and args[0] == "verify":
        kb = [[InlineKeyboardButton("Verify", callback_data="user_verify")]]
        await update.message.reply_text(start_text_for_user(), reply_markup=InlineKeyboardMarkup(kb))
        return

    if is_admin(update):
        kb = [[InlineKeyboardButton("Configure Project", callback_data="admin_config")]]
        await update.message.reply_text(
            f"Hello @{update.effective_user.username}! You're authorized.\nChoose an option:",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return

    kb = [[InlineKeyboardButton("Verify", callback_data="user_verify")]]
    await update.message.reply_text(start_text_for_user(), reply_markup=InlineKeyboardMarkup(kb))


async def send_channel_pin(context: ContextTypes.DEFAULT_TYPE):
    project = get_latest_project()
    if not project:
        logger.info("send_channel_pin: no project configured")
        return
    project_id, network, contract, group_link, channel_id = project

    keyboard = [
        [InlineKeyboardButton("✅ Verify Now", url=f"https://t.me/{BOT_USERNAME}?start=verify")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        msg = await context.bot.send_message(
            chat_id=channel_id,
            text=(
                "🚀 Welcome!\n\n"
                "🔒 Holders-only group requires verification.\n\n"
                "Click below to verify:"
            ),
            reply_markup=reply_markup,
        )
        await context.bot.pin_chat_message(chat_id=channel_id, message_id=msg.message_id, disable_notification=True)
        logger.info("Pinned verification message to channel %s", channel_id)
    except Exception as exc:
        logger.exception("Could not post/pin in channel %s: %s", channel_id, exc)


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
        rows, row = [], []
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
        await q.edit_message_text(
            f"Selected **{NETWORKS.get(net, net)}**.\n\nSend the *contract address/mint* as a message."
        )
        return

    if data == "user_verify":
        a, b = random.randint(2, 9), random.randint(2, 9)
        upsert_state(q.from_user.id, "VERIFY_MATH", json.dumps({"answer": a + b}))
        await q.edit_message_text(f"Human check: What is {a} + {b}?")
        return


async def _make_retry_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Verify", callback_data="user_verify")]])


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    uid = update.effective_user.id
    state, payload = get_state(uid)

    # --- Admin flows ---
    if state == "SET_CONTRACT":
        data = json.loads(payload or "{}")
        data["contract"] = text
        upsert_state(uid, "SET_GROUP_LINK", json.dumps(data))

        dex = get_dexscreener_info(text) or {}
        cg_platform = {"eth": "ethereum", "bsc": "binance-smart-chain", "base": "base", "sol": "solana"}.get(
            data["network"]
        )
        cg = get_coingecko_info(cg_platform, text) if cg_platform else {}

        info = ["Got contract."]
        if dex:
            info.append(f"• Dexscreener: {dex.get('symbol')} {dex.get('priceUsd')} FDV: {dex.get('fdv')}")
        if cg:
            info.append(f"• CoinGecko: ${cg.get('priceUsd')} MC: {cg.get('marketCap')}")

        await update.message.reply_text(
            "\n".join(info)
            + "\n\nSend the *private group invite link* or type 'NO_LINK' if you'd like auto-approve join requests."
        )
        return

    if state == "SET_GROUP_LINK":
        data = json.loads(payload or "{}")
        data["group_link"] = text
        upsert_state(uid, "SET_CHANNEL", json.dumps(data))
        await update.message.reply_text(
            "Got the group link.\n\nNow send the *channel username* (e.g. @MyChannel) or chat_id (e.g. -100123456789)."
        )
        return

    if state == "SET_CHANNEL":
        data = json.loads(payload or "{}")
        channel_id = text.strip()
        with db() as con, con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO projects (owner_username, network, contract_address, group_invite_link, channel_chat_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (network, contract_address) DO UPDATE
                SET owner_username = EXCLUDED.owner_username,
                    group_invite_link = EXCLUDED.group_invite_link,
                    channel_chat_id = EXCLUDED.channel_chat_id
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
        try:
            await send_channel_pin(context)
        except Exception as e:
            logger.exception("Error posting pin: %s", e)
            await update.message.reply_text(f"⚠️ Could not post in channel: {e}")
        return

    # --- Verification: math ---
    if state == "VERIFY_MATH":
        data = json.loads(payload or "{}")
        try:
            if int(text) == int(data.get("answer")):
                upsert_state(uid, "VERIFY_WALLET", "{}")
                await update.message.reply_text("✅ Human check passed.\nNow send your **wallet address**:")
            else:
                await update.message.reply_text("❌ Wrong answer. Tap Verify to try again.", reply_markup=await _make_retry_kb())
                upsert_state(uid, None, None)
        except ValueError:
            await update.message.reply_text("Please reply with a number.")
        return

    # --- Verification: wallet ---
    if state == "VERIFY_WALLET":
        wallet = text.strip()
        project = get_latest_project()
        if not project:
            await update.message.reply_text("No project configured yet. Please try later.")
            upsert_state(uid, None, None)
            return
        project_id, network, contract, group_link, channel_id = project

        if network in ("eth", "base", "bsc") and not re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet):
            await update.message.reply_text("That doesn't look like a valid EVM address. Try again:")
            return

        try:
            holder = is_token_holder(network, wallet, contract, DEFAULT_MIN_AMOUNT)
        except Exception as exc:
            logger.exception("Error checking token holder: %s", exc)
            await update.message.reply_text("⚠️ Error checking wallet. Please try again later.")
            upsert_state(uid, None, None)
            return

        if holder:
            save_verified_user(uid, update.effective_user.username or "", project_id, wallet)

            approved = False
            if channel_id and str(channel_id).lower() not in ("", "none"):
                try:
                    await context.bot.approve_chat_join_request(chat_id=channel_id, user_id=uid)
                    approved = True
                except Exception as exc:
                    logger.exception("approve_chat_join_request failed: %s", exc)

            if approved:
                await update.message.reply_text("✅ Verified and approved to join the group.")
            elif group_link and group_link.upper() != "NO_LINK":
                await update.message.reply_text(f"✅ Verified holder.\nHere is your private group link:\n{group_link}")
            else:
                await update.message.reply_text(
                    "✅ Verified holder, but no invite link was configured and auto-approve failed.\n"
                    "Please ask an admin to add you."
                )
        else:
            await update.message.reply_text("❌ You don't appear to hold the token.", reply_markup=await _make_retry_kb())

        upsert_state(uid, None, None)
        return

    # --- Fallback ---
    if is_admin(update):
        await update.message.reply_text("You're an admin. Use /admin to configure a project.")
    else:
        await update.message.reply_text("Tap **Verify** to begin.", reply_markup=await _make_retry_kb())
