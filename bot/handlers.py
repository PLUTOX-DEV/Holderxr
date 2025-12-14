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
    get_all_projects,
    save_verified_user,
    get_verified_users,
    delete_project,
)
from .blockchain import is_token_holder

logger = logging.getLogger(__name__)

# ---------------------------
# Helpers
# ---------------------------

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

def join_community_kb(group_link: str):
    if not group_link or group_link.upper() == "NO_LINK":
        return verify_kb()
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("👥 Join Community", url=group_link)]]
    )

# ---------------------------
# Commands
# ---------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if args and args[0] == "verify":
        await update.message.reply_text(
            "🚀 Token Holder Verification\n\nThis community is restricted to real holders only.\n\n👇 Tap ✅ Verify to begin.",
            reply_markup=verify_kb(),
            parse_mode=None,
        )
        return

    if is_admin(update):
        await cmd_admin(update, context)
        return

    project = get_latest_project()
    group_link = project.get("group_invite_link") if project else None
    await update.message.reply_text(
        "🚀 Welcome! Verify to join the community.",
        reply_markup=join_community_kb(group_link),
        parse_mode=None,
    )

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ You are not authorized.", parse_mode=None)
        return

    await update.message.reply_text(
        "🧠 Admin Dashboard",
        reply_markup=admin_dashboard_kb(),
        parse_mode=None,
    )

# ---------------------------
# Channel Pin / Ad
# ---------------------------

async def send_channel_pin(context: ContextTypes.DEFAULT_TYPE):
    project = get_latest_project()
    if not project:
        return

    network = project["network"]
    contract = project["contract_address"]
    group_link = project.get("group_invite_link")
    channel_id = project.get("channel_chat_id")

    text = (
        "🚀 HOLDERS-ONLY ACCESS\n\n"
        "This group is protected by an on-chain verification bot.\n\n"
        "🔐 Requirements:\n"
        "• Human verification\n"
        "• Token holder check\n\n"
        f"🌐 Network: {NETWORKS.get(network, network)}\n"
        f"📄 Contract: {contract}\n\n"
        "👇 Click below to verify and join"
    )

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Verify Now", url=f"https://t.me/{BOT_USERNAME}?start=verify")]]
    )

    msg = await context.bot.send_message(
        chat_id=channel_id,
        text=text,
        reply_markup=kb,
        parse_mode=None,
    )
    await context.bot.pin_chat_message(channel_id, msg.message_id, disable_notification=True)

# ---------------------------
# Button Handlers
# ---------------------------

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "admin_project":
        projects = get_all_projects()
        if not projects:
            await q.edit_message_text("No projects configured.", parse_mode=None)
            return

        rows = [
            [InlineKeyboardButton(f"{p['network']}-{p['contract_address'][:6]}...", callback_data=f"project:{p['id']}")]
            for p in projects
        ]

        await q.edit_message_text(
            "Select a project to view / edit:",
            reply_markup=InlineKeyboardMarkup(rows),
            parse_mode=None
        )
        return

    if data.startswith("project:"):
        project_id = int(data.split(":")[1])
        project = next((p for p in get_all_projects() if p["id"] == project_id), None)
        if not project:
            await q.edit_message_text("Project not found.", parse_mode=None)
            return

        owner = project["owner_username"]
        network = project["network"]
        contract = project["contract_address"]
        group_link = project.get("group_invite_link")
        channel_id = project.get("channel_chat_id")

        text = (
            f"📊 Project Info\n\n"
            f"• Owner: {owner}\n"
            f"• Network: {network}\n"
            f"• Contract: {contract}\n"
            f"• Group Link: {group_link or 'NO_LINK'}\n"
            f"• Channel ID: {channel_id}\n\n"
            f"Select an action:"
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Edit", callback_data=f"edit:{project_id}")],
            [InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{project_id}")],
            [InlineKeyboardButton("⬅ Back", callback_data="admin_project")],
        ])
        await q.edit_message_text(text, reply_markup=kb, parse_mode=None)
        return

    if data.startswith("delete:"):
        project_id = int(data.split(":")[1])
        delete_project(project_id)
        await q.edit_message_text("✅ Project deleted.", parse_mode=None)
        await on_button(update, context)
        return

    if data.startswith("edit:"):
        project_id = int(data.split(":")[1])
        upsert_state(q.from_user.id, "EDIT_PROJECT_CONTRACT", json.dumps({"project_id": project_id}))
        await q.edit_message_text("Send the new contract address for this project:", parse_mode=None)
        return

    if data == "admin_stats":
        users = get_verified_users()
        user_list = "\n".join(f"• {u['username']} ({u['wallet_address']})" for u in users)
        text = f"👥 Verified Users\n\nTotal: {len(users)}\n\n{user_list or 'No verified users yet.'}"
        await q.edit_message_text(text, parse_mode=None, reply_markup=admin_dashboard_kb())
        return

    if data == "admin_repin":
        await send_channel_pin(context)
        await q.edit_message_text("📣 Verification ad re-pinned successfully.", reply_markup=admin_dashboard_kb(), parse_mode=None)
        return

    if data == "user_verify":
        a, b = random.randint(2, 9), random.randint(2, 9)
        upsert_state(q.from_user.id, "VERIFY_MATH", json.dumps({"answer": a + b}))
        await q.edit_message_text(f"🧠 Human check: {a} + {b} ?", parse_mode=None)
        return

# ---------------------------
# Message Handlers
# ---------------------------

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    uid = update.effective_user.id
    state, payload = get_state(uid)

    # EDIT PROJECT FLOW
    if state == "EDIT_PROJECT_CONTRACT":
        data = json.loads(payload or "{}")
        project_id = data["project_id"]
        with db() as con, con.cursor() as cur:
            cur.execute("UPDATE projects SET contract_address=%s WHERE id=%s", (text, project_id))
        upsert_state(uid, "EDIT_PROJECT_GROUP", json.dumps({"project_id": project_id}))
        await update.message.reply_text("✅ Contract updated. Send the new group link or NO_LINK.", parse_mode=None)
        return

    if state == "EDIT_PROJECT_GROUP":
        data = json.loads(payload or "{}")
        project_id = data["project_id"]
        with db() as con, con.cursor() as cur:
            cur.execute("UPDATE projects SET group_invite_link=%s WHERE id=%s", (text, project_id))
        upsert_state(uid, "EDIT_PROJECT_CHANNEL", json.dumps({"project_id": project_id}))
        await update.message.reply_text("✅ Group link updated. Send the new channel username or chat_id.", parse_mode=None)
        return

    if state == "EDIT_PROJECT_CHANNEL":
        data = json.loads(payload or "{}")
        project_id = data["project_id"]
        with db() as con, con.cursor() as cur:
            cur.execute("UPDATE projects SET channel_chat_id=%s WHERE id=%s", (text, project_id))
        upsert_state(uid, None, None)
        await update.message.reply_text("✅ Project fully updated!", parse_mode=None)
        return

    # VERIFY MATH
    if state == "VERIFY_MATH":
        data = json.loads(payload or "{}")
        if text.isdigit() and int(text) == int(data["answer"]):
            upsert_state(uid, "VERIFY_WALLET", "{}")
            await update.message.reply_text("✅ Passed. Send wallet address:", parse_mode=None)
        else:
            upsert_state(uid, None, None)
            await update.message.reply_text("❌ Wrong answer.", reply_markup=verify_kb(), parse_mode=None)
        return

    # VERIFY WALLET
    if state == "VERIFY_WALLET":
        project = get_latest_project()
        if not project:
            await update.message.reply_text("No project configured.", parse_mode=None)
            return

        project_id = project["id"]
        network = project["network"]
        contract = project["contract_address"]
        group_link = project.get("group_invite_link")
        channel_id = project.get("channel_chat_id")

        if network in ("eth", "base", "bsc") and not re.fullmatch(r"0x[a-fA-F0-9]{40}", text):
            await update.message.reply_text("Invalid wallet address.", parse_mode=None)
            return

        if not is_token_holder(network, text, contract, DEFAULT_MIN_AMOUNT):
            await update.message.reply_text("❌ You do not hold the token.", reply_markup=verify_kb(), parse_mode=None)
            return

        save_verified_user(uid, update.effective_user.username or "", project_id, text)

        approved = False
        if channel_id and str(channel_id).lower() not in ("", "none"):
            try:
                await context.bot.approve_chat_join_request(chat_id=channel_id, user_id=uid)
                approved = True
            except Exception:
                pass

        if approved:
            await update.message.reply_text("🎉 Verified! Auto-approved to join the group.", parse_mode=None)
        else:
            await update.message.reply_text(
                "🎉 Verified!\nUse the button below to join the community.",
                reply_markup=join_community_kb(group_link),
                parse_mode=None,
            )

        upsert_state(uid, None, None)
        return

    # FALLBACK
    project = get_latest_project()
    group_link = project.get("group_invite_link") if project else None
    await update.message.reply_text(
        "Tap ✅ Verify to start verification.",
        reply_markup=join_community_kb(group_link),
        parse_mode=None,
    )
