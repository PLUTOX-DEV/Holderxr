from __future__ import annotations
import json
import random
import logging
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .config import ADMIN_USERNAMES, NETWORKS, DEFAULT_MIN_AMOUNT, BOT_USERNAME
from .db import (
    db,
    upsert_state,
    get_state,
    get_latest_project,
    save_verified_user,
)
from .market import get_dexscreener_info, get_coingecko_info
from .blockchain import is_token_holder

logger = logging.getLogger(__name__)


# -------------------------------------------------
# Helpers
# -------------------------------------------------

def is_admin(update: Update) -> bool:
    u = update.effective_user
    return bool(u and u.username and u.username in ADMIN_USERNAMES)


def verify_kb():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Verify", callback_data="user_verify")]]
    )


def admin_dashboard_kb():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 Project Info", callback_data="admin_project")],
            [InlineKeyboardButton("👥 Verified Users", callback_data="admin_stats")],
            [InlineKeyboardButton("📣 Re-Pin Verification Ad", callback_data="admin_repin")],
            [InlineKeyboardButton("⚙️ Configure Project", callback_data="admin_config")],
        ]
    )


def start_text_for_user() -> str:
    return (
        "🚀 *Token Holder Verification*\n\n"
        "This community is restricted to *real holders only*.\n\n"
        "👇 Tap **Verify** to begin."
    )


# -------------------------------------------------
# Commands
# -------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    # Deep link verify
    if args and args[0] == "verify":
        await update.message.reply_text(
            start_text_for_user(),
            reply_markup=verify_kb(),
            parse_mode="Markdown",
        )
        return

    # Admin start
    if is_admin(update):
        await update.message.reply_text(
            "🧠 *Admin Dashboard*",
            reply_markup=admin_dashboard_kb(),
            parse_mode="Markdown",
        )
        return

    # Normal user
    await update.message.reply_text(
        start_text_for_user(),
        reply_markup=verify_kb(),
        parse_mode="Markdown",
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ You are not authorized.")
        return

    await update.message.reply_text(
        "🧠 *Admin Dashboard*",
        reply_markup=admin_dashboard_kb(),
        parse_mode="Markdown",
    )


# -------------------------------------------------
# Channel Pin / Ad
# -------------------------------------------------

async def send_channel_pin(context: ContextTypes.DEFAULT_TYPE):
    project = get_latest_project()
    if not project:
        return

    _, network, contract, _, channel_id = project

    text = (
        "🚀 *HOLDERS-ONLY ACCESS*\n\n"
        "This group is protected by an on-chain verification bot.\n\n"
        "🔐 Requirements:\n"
        "• Human verification\n"
        "• Token holder check\n\n"
        f"🌐 Network: *{NETWORKS.get(network, network)}*\n"
        f"📄 Contract:\n`{contract}`\n\n"
        "👇 Click below to verify and join"
    )

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Verify Now", url=f"https://t.me/{BOT_USERNAME}?start=verify")]]
    )

    msg = await context.bot.send_message(
        chat_id=channel_id,
        text=text,
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await context.bot.pin_chat_message(channel_id, msg.message_id, disable_notification=True)


# -------------------------------------------------
# Buttons
# -------------------------------------------------

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    # ---------- ADMIN ----------
    if data == "admin_project":
        project = get_latest_project()
        if not project:
            await q.edit_message_text("No project configured.")
            return

        _, network, contract, group_link, channel_id = project
        await q.edit_message_text(
            "📊 *Current Project*\n\n"
            f"• Network: {NETWORKS.get(network, network)}\n"
            f"• Contract:\n`{contract}`\n"
            f"• Group Link: {group_link}\n"
            f"• Channel ID: `{channel_id}`",
            parse_mode="Markdown",
            reply_markup=admin_dashboard_kb(),
        )
        return

    if data == "admin_stats":
        with db() as con, con.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()[0]

        await q.edit_message_text(
            f"👥 *Verified Users*\n\nTotal verified holders: **{count}**",
            parse_mode="Markdown",
            reply_markup=admin_dashboard_kb(),
        )
        return

    if data == "admin_repin":
        await send_channel_pin(context)
        await q.edit_message_text(
            "📣 Verification ad re-pinned successfully.",
            reply_markup=admin_dashboard_kb(),
        )
        return

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

    # ---------- USER VERIFY ----------
    if data == "user_verify":
        a, b = random.randint(2, 9), random.randint(2, 9)
        upsert_state(q.from_user.id, "VERIFY_MATH", json.dumps({"answer": a + b}))
        await q.edit_message_text(f"🧠 Human check: *{a} + {b}* ?", parse_mode="Markdown")
        return


# -------------------------------------------------
# Messages
# -------------------------------------------------

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    uid = update.effective_user.id
    state, payload = get_state(uid)

    # ---------- ADMIN SETUP ----------
    if state == "SET_CONTRACT":
        data = json.loads(payload or "{}")
        data["contract"] = text
        upsert_state(uid, "SET_GROUP_LINK", json.dumps(data))

        await update.message.reply_text(
            "✅ Contract saved.\n\nSend the *private group invite link* or `NO_LINK`."
        )
        return

    if state == "SET_GROUP_LINK":
        data = json.loads(payload or "{}")
        data["group_link"] = text
        upsert_state(uid, "SET_CHANNEL", json.dumps(data))

        await update.message.reply_text(
            "Now send the *channel username* or *chat_id*."
        )
        return

    if state == "SET_CHANNEL":
        data = json.loads(payload or "{}")
        with db() as con, con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO projects (owner_username, network, contract_address, group_invite_link, channel_chat_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (network, contract_address) DO UPDATE
                SET group_invite_link = EXCLUDED.group_invite_link,
                    channel_chat_id = EXCLUDED.channel_chat_id
                """,
                (
                    update.effective_user.username or "",
                    data["network"],
                    data["contract"],
                    data["group_link"],
                    text,
                ),
            )

        upsert_state(uid, None, None)
        await update.message.reply_text("✅ Project saved. Verification ad will be pinned.")
        await send_channel_pin(context)
        return

    # ---------- VERIFY ----------
    if state == "VERIFY_MATH":
        data = json.loads(payload or "{}")
        if text.isdigit() and int(text) == int(data["answer"]):
            upsert_state(uid, "VERIFY_WALLET", "{}")
            await update.message.reply_text("✅ Passed. Send wallet address:")
        else:
            upsert_state(uid, None, None)
            await update.message.reply_text("❌ Wrong answer.", reply_markup=verify_kb())
        return

    if state == "VERIFY_WALLET":
        project = get_latest_project()
        if not project:
            await update.message.reply_text("No project configured.")
            return

        project_id, network, contract, group_link, channel_id = project

        if network in ("eth", "base", "bsc") and not re.fullmatch(r"0x[a-fA-F0-9]{40}", text):
            await update.message.reply_text("Invalid wallet address.")
            return

        if not is_token_holder(network, text, contract, DEFAULT_MIN_AMOUNT):
            await update.message.reply_text("❌ You do not hold the token.", reply_markup=verify_kb())
            return

        save_verified_user(uid, update.effective_user.username or "", project_id, text)

        try:
            await context.bot.approve_chat_join_request(channel_id, uid)
        except Exception:
            pass

        await update.message.reply_text("🎉 Verified! Welcome to the community.")
        upsert_state(uid, None, None)
        return

    await update.message.reply_text("Tap Verify to begin.", reply_markup=verify_kb())
