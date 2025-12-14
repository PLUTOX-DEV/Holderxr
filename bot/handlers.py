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

# ===========================
# Commands
# ===========================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if args and args[0] == "verify":
        await update.message.reply_text(
            "🚀 Token Holder Verification\n\n"
            "This community is restricted to real holders only.\n\n"
            "👇 Tap ✅ Verify to begin.",
            reply_markup=verify_kb(),
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
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ You are not authorized.")
        return

    await update.message.reply_text(
        "🧠 Admin Dashboard",
        reply_markup=admin_dashboard_kb(),
    )

# ===========================
# Channel Pin
# ===========================

async def send_channel_pin(context: ContextTypes.DEFAULT_TYPE):
    project = get_latest_project()
    if not project:
        return

    network = project["network"]
    contract = project["contract_address"]
    channel_id = project.get("channel_chat_id")

    if not channel_id:
        return

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
    )

    await context.bot.pin_chat_message(
        chat_id=channel_id,
        message_id=msg.message_id,
        disable_notification=True,
    )

# ===========================
# Button Handlers
# ===========================

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    # ---------- CONFIG PROJECT ----------
    if data == "admin_config":
        upsert_state(q.from_user.id, "CFG_OWNER", "{}")
        await q.edit_message_text(
            "⚙️ Configure New Project\n\n"
            "Send *owner username* (without @):",
            parse_mode="Markdown",
        )
        return

    # ---------- PROJECT LIST ----------
    if data == "admin_project":
        projects = get_all_projects()
        if not projects:
            await q.edit_message_text("No projects configured.")
            return

        rows = [
            [InlineKeyboardButton(
                f"{p['network']}-{p['contract_address'][:6]}...",
                callback_data=f"project:{p['id']}"
            )]
            for p in projects
        ]

        await q.edit_message_text(
            "Select a project:",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    # ---------- PROJECT VIEW ----------
    if data.startswith("project:"):
        pid = int(data.split(":")[1])
        project = next((p for p in get_all_projects() if p["id"] == pid), None)

        if not project:
            await q.edit_message_text("Project not found.")
            return

        text = (
            f"📊 Project Info\n\n"
            f"• Owner: {project['owner_username']}\n"
            f"• Network: {project['network']}\n"
            f"• Contract: {project['contract_address']}\n"
            f"• Group: {project.get('group_invite_link') or 'NO_LINK'}\n"
            f"• Channel: {project.get('channel_chat_id')}\n"
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Edit", callback_data=f"edit:{pid}")],
            [InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{pid}")],
            [InlineKeyboardButton("⬅ Back", callback_data="admin_project")],
        ])

        await q.edit_message_text(text, reply_markup=kb)
        return

    if data.startswith("delete:"):
        delete_project(int(data.split(":")[1]))
        await q.edit_message_text("✅ Project deleted.", reply_markup=admin_dashboard_kb())
        return

    if data.startswith("edit:"):
        pid = int(data.split(":")[1])
        upsert_state(q.from_user.id, "EDIT_PROJECT_CONTRACT", json.dumps({"project_id": pid}))
        await q.edit_message_text("Send new contract address:")
        return

    if data == "admin_stats":
        users = get_verified_users()
        text = "\n".join(f"• {u['username']} — {u['wallet_address']}" for u in users)
        await q.edit_message_text(
            f"👥 Verified Users ({len(users)})\n\n{text or 'None'}",
            reply_markup=admin_dashboard_kb(),
        )
        return

    if data == "admin_repin":
        await send_channel_pin(context)
        await q.edit_message_text("📣 Ad re-pinned.", reply_markup=admin_dashboard_kb())
        return

    if data == "user_verify":
        a, b = random.randint(2, 9), random.randint(2, 9)
        upsert_state(q.from_user.id, "VERIFY_MATH", json.dumps({"answer": a + b}))
        await q.edit_message_text(f"🧠 Human check: {a} + {b} ?")
        return

# ===========================
# Message Handlers
# ===========================

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    uid = update.effective_user.id
    state, payload = get_state(uid)

    # ---------- CONFIG PROJECT FLOW ----------
    if state == "CFG_OWNER":
        with db() as con, con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO projects (owner_username, network, contract_address)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (text, "eth", "0x0000000000000000000000000000000000000000"),
            )
            pid = cur.fetchone()[0]

        upsert_state(uid, "CFG_NETWORK", json.dumps({"project_id": pid}))
        await update.message.reply_text("Send network (eth / bsc / base):")
        return

    if state == "CFG_NETWORK":
        if text not in NETWORKS:
            await update.message.reply_text("Invalid network. Try again.")
            return

        pid = json.loads(payload)["project_id"]
        with db() as con, con.cursor() as cur:
            cur.execute("UPDATE projects SET network=%s WHERE id=%s", (text, pid))

        upsert_state(uid, "CFG_CONTRACT", json.dumps({"project_id": pid}))
        await update.message.reply_text("Send contract address:")
        return

    if state == "CFG_CONTRACT":
        pid = json.loads(payload)["project_id"]
        with db() as con, con.cursor() as cur:
            cur.execute("UPDATE projects SET contract_address=%s WHERE id=%s", (text, pid))

        upsert_state(uid, "CFG_GROUP", json.dumps({"project_id": pid}))
        await update.message.reply_text("Send group invite link or NO_LINK:")
        return

    if state == "CFG_GROUP":
        pid = json.loads(payload)["project_id"]
        with db() as con, con.cursor() as cur:
            cur.execute("UPDATE projects SET group_invite_link=%s WHERE id=%s", (text, pid))

        upsert_state(uid, "CFG_CHANNEL", json.dumps({"project_id": pid}))
        await update.message.reply_text("Send channel chat_id or username:")
        return

    if state == "CFG_CHANNEL":
        pid = json.loads(payload)["project_id"]
        with db() as con, con.cursor() as cur:
            cur.execute("UPDATE projects SET channel_chat_id=%s WHERE id=%s", (text, pid))

        upsert_state(uid, None, None)
        await update.message.reply_text("🎉 Project configured!", reply_markup=admin_dashboard_kb())
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
        if not project:
            return

        if not is_token_holder(
            project["network"],
            text,
            project["contract_address"],
            DEFAULT_MIN_AMOUNT,
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

    # FALLBACK
    project = get_latest_project()
    group_link = project.get("group_invite_link") if project else None
    await update.message.reply_text(
        "Tap ✅ Verify to start verification.",
        reply_markup=join_community_kb(group_link),
        parse_mode=None,
    )
