from __future__ import annotations
import json
import random
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from .config import ADMIN_USERNAMES, NETWORKS, DEFAULT_MIN_AMOUNT, BOT_USERNAME
from .db import (
    db,
    upsert_state,
    get_state,
    get_latest_project,
    get_all_projects,
    save_verified_user,
    get_verified_users,
    delete_project,
)
from .blockchain import is_token_holder, get_token_meta

logger = logging.getLogger(__name__)

# ===========================
# Helpers
# ===========================

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

def join_community_kb(group_link: str | None):
    if not group_link or group_link.upper() == "NO_LINK":
        return verify_kb()
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("👥 Join Community", url=group_link)]]
    )

def network_select_kb():
    rows, row = [], []
    for key, label in NETWORKS.items():
        row.append(InlineKeyboardButton(label, callback_data=f"cfg_network:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)

async def safe_edit(q, text, reply_markup=None, parse_mode=None):
    """Safely edit message to avoid 'Message not modified' errors"""
    try:
        await q.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise

# ===========================
# Commands
# ===========================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args and args[0] == "verify":
        await update.message.reply_text(
            "🚀 <b>Token Holder Verification</b>\n\nTap below to start.",
            reply_markup=verify_kb(),
            parse_mode="HTML",
        )
        return

    if is_admin(update):
        await cmd_admin(update, context)
        return

    project = get_latest_project()
    await update.message.reply_text(
        "🚀 Welcome! Verify to join the community.",
        reply_markup=join_community_kb(project.get("group_invite_link") if project else None),
    )

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 <b>Admin Dashboard</b>",
        reply_markup=admin_dashboard_kb(),
        parse_mode="HTML",
    )

# ===========================
# Channel Pin
# ===========================

async def send_channel_pin(context: ContextTypes.DEFAULT_TYPE):
    project = get_latest_project()
    if not project or not project.get("channel_chat_id"):
        return

    text = (
        "🚀 <b>HOLDERS-ONLY ACCESS</b>\n\n"
        f"🌐 <b>Network:</b> {NETWORKS.get(project['network'])}\n"
        f"📄 <b>Contract:</b> <code>{project['contract_address']}</code>\n\n"
        "👇 Click below to verify"
    )

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Verify Now", url=f"https://t.me/{BOT_USERNAME}?start=verify")]]
    )

    msg = await context.bot.send_message(
        chat_id=project["channel_chat_id"],
        text=text,
        reply_markup=kb,
        parse_mode="HTML",
    )

    await context.bot.pin_chat_message(
        chat_id=project["channel_chat_id"],
        message_id=msg.message_id,
        disable_notification=True,
    )

# ===========================
# Button Handlers
# ===========================

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data

    # ---------- ADMIN CONFIG ----------
    if data == "admin_config":
        upsert_state(uid, "CFG_OWNER", "{}")
        await safe_edit(q, "Send <b>owner username</b> (without @):", parse_mode="HTML")
        return

    if data.startswith("cfg_network:"):
        network = data.split(":")[1]
        state, payload = get_state(uid)
        pid = json.loads(payload)["project_id"]

        # Do not update database yet, store network in state
        upsert_state(uid, "CFG_CONTRACT", json.dumps({"project_id": pid, "network": network}))
        await safe_edit(q, "Send contract address:")
        return

    # ---------- CONTRACT CONFIRM ----------
    if data == "confirm_contract":
        state, payload = get_state(uid)
        p = json.loads(payload)

        with db() as con, con.cursor() as cur:
            cur.execute(
                "UPDATE projects SET network=%s, contract_address=%s WHERE id=%s",
                (p["network"], p["contract"], p["project_id"]),
            )

        upsert_state(uid, "CFG_GROUP", json.dumps({"project_id": p["project_id"]}))
        await safe_edit(q, "✅ Contract saved.\nSend group invite link or NO_LINK:")
        return

    if data == "retry_contract":
        upsert_state(uid, "CFG_CONTRACT", get_state(uid)[1])
        await safe_edit(q, "Send contract address again:")
        return

    # ---------- PROJECT LIST ----------
    if data == "admin_project":
        rows = [
            [InlineKeyboardButton(
                f"{NETWORKS.get(p['network'])} • {p['contract_address'][:6]}…",
                callback_data=f"project:{p['id']}"
            )]
            for p in get_all_projects()
        ]
        await safe_edit(q, "Select a project:", reply_markup=InlineKeyboardMarkup(rows))
        return

    # ---------- PROJECT VIEW ----------
    if data.startswith("project:"):
        pid = int(data.split(":")[1])
        p = next(p for p in get_all_projects() if p["id"] == pid)

        text = (
            "<b>📊 Project Info</b>\n\n"
            f"• <b>Owner:</b> @{p['owner_username']}\n"
            f"• <b>Network:</b> {NETWORKS.get(p['network'])}\n"
            f"• <b>Contract:</b> <code>{p['contract_address']}</code>\n"
            f"• <b>Group:</b> {p.get('group_invite_link') or 'Not set'}\n"
            f"• <b>Channel:</b> {p.get('channel_chat_id') or 'Not set'}\n"
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{pid}")],
            [InlineKeyboardButton("⬅ Back", callback_data="admin_project")],
        ])
        await safe_edit(q, text, reply_markup=kb, parse_mode="HTML")
        return

    if data.startswith("delete:"):
        delete_project(int(data.split(":")[1]))
        await safe_edit(q, "✅ Project deleted.", reply_markup=admin_dashboard_kb())
        return

    # ---------- REPIN ----------
    if data == "admin_repin":
        await send_channel_pin(context)
        await safe_edit(q, "📌 Verification post re-pinned.", reply_markup=admin_dashboard_kb())
        return

    # ---------- VERIFY ----------
    if data == "user_verify":
        a, b = random.randint(2, 9), random.randint(2, 9)
        upsert_state(uid, "VERIFY_MATH", json.dumps({"answer": a + b}))
        await safe_edit(q, f"🧠 Human check: {a} + {b} ?")
        return

# ===========================
# Message Handlers
# ===========================

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = (update.message.text or "").strip()
    state, payload = get_state(uid)

    # ---------- CONFIG FLOW ----------
    if state == "CFG_OWNER":
        with db() as con, con.cursor() as cur:
            cur.execute(
                "INSERT INTO projects (owner_username) VALUES (%s) RETURNING id",
                (text,),
            )
            pid = cur.fetchone()[0]

        upsert_state(uid, "CFG_NETWORK", json.dumps({"project_id": pid}))
        await update.message.reply_text("Select network:", reply_markup=network_select_kb())
        return

    if state == "CFG_CONTRACT":
        data_json = json.loads(payload)
        pid = data_json["project_id"]
        network = data_json.get("network", "eth")
        meta = get_token_meta(network, text)

        if not meta:
            await update.message.reply_text("❌ Invalid contract. Send again:")
            return

        upsert_state(
            uid,
            "CFG_CONTRACT_CONFIRM",
            json.dumps({"project_id": pid, "contract": text, "network": network, "meta": meta}),
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm", callback_data="confirm_contract")],
            [InlineKeyboardButton("❌ Re-enter", callback_data="retry_contract")],
        ])

        await update.message.reply_text(
            f"🔎 <b>Token Found</b>\n\n"
            f"Name: <b>{meta['name']}</b>\n"
            f"Symbol: <b>{meta['symbol']}</b>\n\nConfirm this contract?",
            reply_markup=kb,
            parse_mode="HTML",
        )
        return

    if state == "CFG_GROUP":
        pid = json.loads(payload)["project_id"]
        with db() as con, con.cursor() as cur:
            cur.execute("UPDATE projects SET group_invite_link=%s WHERE id=%s", (text, pid))

        upsert_state(uid, "CFG_CHANNEL", json.dumps({"project_id": pid}))
        await update.message.reply_text("Send channel chat_id or @channelusername:")
        return

    if state == "CFG_CHANNEL":
        pid = json.loads(payload)["project_id"]
        with db() as con, con.cursor() as cur:
            cur.execute("UPDATE projects SET channel_chat_id=%s WHERE id=%s", (text, pid))

        upsert_state(uid, None, None)
        await update.message.reply_text("🎉 Project fully configured!", reply_markup=admin_dashboard_kb())
        return

    # ---------- VERIFY ----------
    if state == "VERIFY_MATH":
        if text.isdigit() and int(text) == json.loads(payload)["answer"]:
            upsert_state(uid, "VERIFY_WALLET", "{}")
            await update.message.reply_text("Send wallet address:")
        else:
            upsert_state(uid, None, None)
            await update.message.reply_text("❌ Wrong answer.", reply_markup=verify_kb())
        return

    if state == "VERIFY_WALLET":
        project = get_latest_project()
        if not is_token_holder(
            project["network"], text, project["contract_address"], DEFAULT_MIN_AMOUNT
        ):
            await update.message.reply_text("❌ You do not hold the token.")
            return

        save_verified_user(uid, update.effective_user.username or "", project["id"], text)
        upsert_state(uid, None, None)
        await update.message.reply_text(
            "🎉 Verified!",
            reply_markup=join_community_kb(project.get("group_invite_link")),
        )
        return
