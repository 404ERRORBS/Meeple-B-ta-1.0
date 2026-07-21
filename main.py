"""
Discord XP Bot v2 — Full rewrite
Multi-server, fully button-driven, zero-hardcoded IDs.

Features
--------
• Video share XP — auto-validated (link + screenshot)
• Emoji reaction XP — XP Manager bonus (default emoji: ✅)
• Invitation XP — configurable, announced in XP channel
• Video Streak — consecutive shares, nickname display (🔥N)
• Monthly Quests — 5 rarities (Stone → Diamond), random per user
• Repeatable Boost Quest — Nitro Boost = XP
• Achievements — Discord role rewards, fully configurable
• Events — Double XP, Community Goals
• Shop — images, temporary items, text-input items
• 3 member channels: share / notifications / commands
• Admin channel — internal notifications (expired items, text orders)
• Full /config panel (buttons only)
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import re
import os
import json
import shutil
import random
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional
from flask import Flask
from threading import Thread

# ══════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════

DB_PATH         = "bot_data.db"
BACKUP_REGISTRY = "backup_channels.json"

C_MAIN    = 0x5865F2
C_SUCCESS = 0x57F287
C_ERROR   = 0xED4245
C_GOLD    = 0xFEE75C
C_INFO    = 0x1ABC9C
C_STREAK  = 0xFF6B35
C_QUEST   = 0x9B59B6
C_ACHIEVE = 0xF1C40F
C_EVENT   = 0xE74C3C

RARITIES = ["stone", "bronze", "silver", "gold", "diamond"]
RARITY_EMOJI = {"stone": "🪨", "bronze": "🥉", "silver": "🥈", "gold": "🥇", "diamond": "💎"}
RARITY_COLOR = {
    "stone": 0x95A5A6, "bronze": 0xCD7F32, "silver": 0xBDC3C7,
    "gold": 0xF1C40F,  "diamond": 0x1ABC9C
}

# Quest pool — add more dicts here to extend without code changes
QUEST_POOL = {
    "stone": [
        {"key": "share_5",   "name": "Share 5 videos",                     "type": "share_videos",  "target": 5},
        {"key": "invite_1",  "name": "Invite 1 member",                    "type": "invite_members","target": 1},
        {"key": "streak_5",  "name": "Reach a 5-video streak",             "type": "video_streak",  "target": 5},
        {"key": "first5_1",  "name": "Be among the first 5 supporters once","type": "first_5",      "target": 1},
    ],
    "bronze": [
        {"key": "share_10",  "name": "Share 10 videos",                    "type": "share_videos",  "target": 10},
        {"key": "invite_3",  "name": "Invite 3 members",                   "type": "invite_members","target": 3},
        {"key": "streak_10", "name": "Reach a 10-video streak",            "type": "video_streak",  "target": 10},
        {"key": "first5_3",  "name": "Be among the first 5 supporters 3 times","type": "first_5",  "target": 3},
    ],
    "silver": [
        {"key": "share_20",  "name": "Share 20 videos",                    "type": "share_videos",  "target": 20},
        {"key": "invite_5",  "name": "Invite 5 members",                   "type": "invite_members","target": 5},
        {"key": "streak_20", "name": "Reach a 20-video streak",            "type": "video_streak",  "target": 20},
        {"key": "first5_10", "name": "Be among the first 5 supporters 10 times","type": "first_5", "target": 10},
        {"key": "top1_1",    "name": "Be the #1 supporter once",           "type": "top_1",         "target": 1},
    ],
    "gold": [
        {"key": "share_35",  "name": "Share 35 videos",                    "type": "share_videos",  "target": 35},
        {"key": "invite_10", "name": "Invite 10 members",                  "type": "invite_members","target": 10},
        {"key": "streak_35", "name": "Reach a 35-video streak",            "type": "video_streak",  "target": 35},
        {"key": "top1_3",    "name": "Be the #1 supporter 3 times",        "type": "top_1",         "target": 3},
        {"key": "all_events","name": "Participate in every enabled event this month","type": "all_events","target": 1},
    ],
    "diamond": [
        {"key": "share_50",  "name": "Share 50 videos",                    "type": "share_videos",  "target": 50},
        {"key": "invite_15", "name": "Invite 15 members",                  "type": "invite_members","target": 15},
        {"key": "streak_50", "name": "Reach a 50-video streak",            "type": "video_streak",  "target": 50},
        {"key": "top1_10",   "name": "Be the #1 supporter 10 times",       "type": "top_1",         "target": 10},
        {"key": "all_quests","name": "Complete all 4 monthly quests",        "type": "all_quests",    "target": 4},
    ],
}

# Achievement definitions — add entries to extend
ACHIEVEMENT_DEFS = [
    {"key": "shares",  "name": "Video Supporter", "category": "total_shares",      "tiers": [10, 50, 100, 250, 500]},
    {"key": "invites", "name": "Recruiter",        "category": "total_invites",     "tiers": [1, 5, 10, 25, 50]},
    {"key": "streak",  "name": "On Fire",          "category": "max_streak_ever",   "tiers": [5, 15, 30, 60, 100]},
    {"key": "boosts",  "name": "Server Booster",   "category": "total_boosts",      "tiers": [1, 3, 6, 12, 24]},
    {"key": "quests",  "name": "Quest Master",     "category": "total_quests_done", "tiers": [1, 5, 10, 25, 50]},
]

# ══════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS guild_config (
        guild_id                INTEGER PRIMARY KEY,
        youtube_channel_id      TEXT,
        share_channel_id        INTEGER,
        notification_channel_id INTEGER,
        commands_channel_id     INTEGER,
        admin_channel_id        INTEGER,
        log_channel_id          INTEGER,
        backup_channel_id       INTEGER,
        share_ping_role_id      INTEGER,
        manager_role_id         INTEGER,
        reaction_emoji          TEXT    DEFAULT '✅',
        reaction_xp             INTEGER DEFAULT 50,
        reaction_cooldown_h     INTEGER DEFAULT 1,
        invite_xp               INTEGER DEFAULT 25,
        share_window_min        INTEGER DEFAULT 20,
        streak_enabled          INTEGER DEFAULT 1,
        streak_xp_bonus         INTEGER DEFAULT 2,
        streak_xp_cap           INTEGER DEFAULT 30,
        streak_reset_on_miss    INTEGER DEFAULT 1,
        boost_quest_enabled     INTEGER DEFAULT 1,
        boost_quest_xp          INTEGER DEFAULT 100,
        quest_xp_stone          INTEGER DEFAULT 50,
        quest_xp_bronze         INTEGER DEFAULT 100,
        quest_xp_silver         INTEGER DEFAULT 200,
        quest_xp_gold           INTEGER DEFAULT 400,
        quest_xp_diamond        INTEGER DEFAULT 750,
        achievement_channel_id  INTEGER,
        event_double_xp_mult    REAL    DEFAULT 2.0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS xp_data (
        guild_id INTEGER, user_id INTEGER, xp INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS video_shares (
        guild_id  INTEGER, video_id TEXT, user_id INTEGER,
        shared_at TEXT,    position INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, video_id, user_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS current_video (
        guild_id          INTEGER PRIMARY KEY,
        video_id          TEXT,
        video_url         TEXT,
        video_title       TEXT,
        detected_at       TEXT,
        previous_video_id TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS shop_items (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id      INTEGER,
        name          TEXT,
        price         INTEGER,
        image_url     TEXT,
        is_temporary  INTEGER DEFAULT 0,
        duration_days INTEGER,
        show_duration INTEGER DEFAULT 1,
        requires_text INTEGER DEFAULT 0,
        text_label    TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS inventory (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id     INTEGER,
        user_id      INTEGER,
        item_name    TEXT,
        purchased_at TEXT,
        expires_at   TEXT,
        is_expired   INTEGER DEFAULT 0,
        item_text    TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS reaction_cooldowns (
        guild_id INTEGER, user_id INTEGER, last_reaction TEXT,
        PRIMARY KEY (guild_id, user_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS reaction_messages (
        guild_id     INTEGER, message_id INTEGER, target_uid INTEGER,
        given_by_uid INTEGER, amount INTEGER, given_at TEXT,
        PRIMARY KEY (guild_id, message_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS streaks (
        guild_id       INTEGER,
        user_id        INTEGER,
        current_streak INTEGER DEFAULT 0,
        max_streak     INTEGER DEFAULT 0,
        last_video_id  TEXT,
        PRIMARY KEY (guild_id, user_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS monthly_quests (
        guild_id     INTEGER,
        user_id      INTEGER,
        month_key    TEXT,
        rarity       TEXT,
        quest_key    TEXT,
        quest_type   TEXT,
        quest_target INTEGER,
        quest_name   TEXT,
        progress     INTEGER DEFAULT 0,
        completed    INTEGER DEFAULT 0,
        xp_awarded   INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, month_key, rarity)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS quest_pool_config (
        guild_id  INTEGER, quest_key TEXT, enabled INTEGER DEFAULT 1,
        PRIMARY KEY (guild_id, quest_key)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS achievements (
        guild_id        INTEGER, user_id INTEGER,
        achievement_key TEXT,    tier INTEGER,
        unlocked_at     TEXT,
        PRIMARY KEY (guild_id, user_id, achievement_key, tier)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS achievement_config (
        guild_id        INTEGER, achievement_key TEXT,
        tier            INTEGER, threshold INTEGER,
        role_id         INTEGER, enabled INTEGER DEFAULT 1,
        PRIMARY KEY (guild_id, achievement_key, tier)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id    INTEGER,
        name        TEXT,
        description TEXT,
        event_type  TEXT,
        start_date  TEXT,
        end_date    TEXT,
        config_json TEXT DEFAULT '{}',
        enabled     INTEGER DEFAULT 1
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS community_goals (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id     INTEGER,
        event_id     INTEGER,
        name         TEXT,
        goal_type    TEXT,
        target       INTEGER,
        current      INTEGER DEFAULT 0,
        reward_xp    INTEGER DEFAULT 0,
        contributors TEXT    DEFAULT '[]',
        completed    INTEGER DEFAULT 0,
        enabled      INTEGER DEFAULT 1
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS invites_cache (
        guild_id    INTEGER, invite_code TEXT,
        inviter_id  INTEGER, uses INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, invite_code)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS user_stats (
        guild_id          INTEGER, user_id INTEGER,
        total_shares      INTEGER DEFAULT 0,
        total_invites     INTEGER DEFAULT 0,
        total_boosts      INTEGER DEFAULT 0,
        total_quests_done INTEGER DEFAULT 0,
        max_streak_ever   INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )""")

    conn.commit()

    # Safe migrations for existing databases
    for migration in [
        "ALTER TABLE current_video ADD COLUMN previous_video_id TEXT",
        "ALTER TABLE current_video ADD COLUMN deadline_ts INTEGER",
        "ALTER TABLE shop_items ADD COLUMN image_url TEXT",
        "ALTER TABLE shop_items ADD COLUMN is_temporary INTEGER DEFAULT 0",
        "ALTER TABLE shop_items ADD COLUMN duration_days INTEGER",
        "ALTER TABLE shop_items ADD COLUMN show_duration INTEGER DEFAULT 1",
        "ALTER TABLE shop_items ADD COLUMN requires_text INTEGER DEFAULT 0",
        "ALTER TABLE shop_items ADD COLUMN text_label TEXT",
        "ALTER TABLE shop_items ADD COLUMN notify_admin INTEGER DEFAULT 0",
        "ALTER TABLE inventory ADD COLUMN purchased_at TEXT",
        "ALTER TABLE inventory ADD COLUMN expires_at TEXT",
        "ALTER TABLE inventory ADD COLUMN is_expired INTEGER DEFAULT 0",
        "ALTER TABLE inventory ADD COLUMN item_text TEXT",
        "ALTER TABLE video_shares ADD COLUMN position INTEGER DEFAULT 0",
        # DM & Welcome features
        "ALTER TABLE guild_config ADD COLUMN info_channel_id INTEGER",
        "ALTER TABLE guild_config ADD COLUMN info_message_id INTEGER",
        "ALTER TABLE guild_config ADD COLUMN welcome_dm_enabled INTEGER DEFAULT 0",
        "ALTER TABLE guild_config ADD COLUMN welcome_dm_role_id INTEGER",
        "ALTER TABLE guild_config ADD COLUMN welcome_dm_on_role_id INTEGER",
        "ALTER TABLE guild_config ADD COLUMN streak_reminder_enabled INTEGER DEFAULT 0",
        "ALTER TABLE guild_config ADD COLUMN server_welcome_enabled INTEGER DEFAULT 0",
        "ALTER TABLE guild_config ADD COLUMN server_welcome_channel_id INTEGER",
        "ALTER TABLE guild_config ADD COLUMN server_welcome_on_role_id INTEGER",
    ]:
        try:
            conn.execute(migration)
        except Exception:
            pass
    conn.commit()
    conn.close()

# ── Config helpers ─────────────────────────────────────────────

def db_get_config(guild_id: int) -> dict:
    conn = get_db()
    row = conn.execute("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,)).fetchone()
    conn.close()
    return dict(row) if row else {}

def db_ensure_config(guild_id: int):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))
    conn.commit()
    conn.close()

def db_set_config(guild_id: int, **kwargs):
    db_ensure_config(guild_id)
    conn = get_db()
    for key, val in kwargs.items():
        conn.execute(f"UPDATE guild_config SET {key}=? WHERE guild_id=?", (val, guild_id))
    conn.commit()
    conn.close()

# ── XP helpers ─────────────────────────────────────────────────

def db_get_xp(guild_id: int, user_id: int) -> int:
    conn = get_db()
    row = conn.execute("SELECT xp FROM xp_data WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
    conn.close()
    return row["xp"] if row else 0

def db_add_xp(guild_id: int, user_id: int, amount: int) -> int:
    conn = get_db()
    conn.execute("""INSERT INTO xp_data (guild_id, user_id, xp) VALUES (?,?,?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = xp + ?""",
                 (guild_id, user_id, amount, amount))
    conn.commit()
    new_xp = conn.execute("SELECT xp FROM xp_data WHERE guild_id=? AND user_id=?",
                          (guild_id, user_id)).fetchone()["xp"]
    conn.close()
    return max(0, new_xp)

def db_set_xp(guild_id: int, user_id: int, amount: int):
    conn = get_db()
    conn.execute("""INSERT INTO xp_data (guild_id, user_id, xp) VALUES (?,?,?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET xp=?""",
                 (guild_id, user_id, amount, amount))
    conn.commit()
    conn.close()

def db_top_xp(guild_id: int, limit: int = 10) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT user_id, xp FROM xp_data WHERE guild_id=? ORDER BY xp DESC LIMIT ?",
        (guild_id, limit)
    ).fetchall()
    conn.close()
    return [(r["user_id"], r["xp"]) for r in rows]

# ── Video share helpers ────────────────────────────────────────

def db_has_shared(guild_id: int, video_id: str, user_id: int) -> bool:
    conn = get_db()
    row = conn.execute("SELECT 1 FROM video_shares WHERE guild_id=? AND video_id=? AND user_id=?",
                       (guild_id, video_id, user_id)).fetchone()
    conn.close()
    return row is not None

def db_add_share(guild_id: int, video_id: str, user_id: int) -> int:
    """Returns the position (1 = first, 2 = second, ...)"""
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*)+1 AS pos FROM video_shares WHERE guild_id=? AND video_id=?",
        (guild_id, video_id)
    ).fetchone()
    pos = row["pos"] if row else 1
    conn.execute(
        "INSERT OR IGNORE INTO video_shares (guild_id, video_id, user_id, shared_at, position) VALUES (?,?,?,?,?)",
        (guild_id, video_id, user_id, datetime.now().isoformat(), pos)
    )
    conn.commit()
    conn.close()
    return pos

def db_get_current_video(guild_id: int) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM current_video WHERE guild_id=?", (guild_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def db_set_current_video(guild_id: int, video_id: str, video_url: str, video_title: str):
    conn = get_db()
    now = datetime.now().isoformat()
    old = conn.execute("SELECT video_id FROM current_video WHERE guild_id=?", (guild_id,)).fetchone()
    prev = old["video_id"] if old else None
    conn.execute("""INSERT INTO current_video (guild_id, video_id, video_url, video_title, detected_at, previous_video_id)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                    video_id=?, video_url=?, video_title=?, detected_at=?, previous_video_id=?""",
                 (guild_id, video_id, video_url, video_title, now, prev,
                  video_id, video_url, video_title, now, prev))
    conn.commit()
    conn.close()

# ── Shop / Inventory helpers ───────────────────────────────────

def db_get_shop_items(guild_id: int) -> list:
    conn = get_db()
    rows = conn.execute("SELECT * FROM shop_items WHERE guild_id=? ORDER BY price ASC", (guild_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_add_shop_item(guild_id: int, name: str, price: int, image_url: str = None,
                     is_temporary: int = 0, duration_days: int = None,
                     show_duration: int = 1, requires_text: int = 0, text_label: str = None,
                     notify_admin: int = 0) -> int:
    conn = get_db()
    c = conn.execute(
        """INSERT INTO shop_items
           (guild_id, name, price, image_url, is_temporary, duration_days, show_duration,
            requires_text, text_label, notify_admin)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (guild_id, name, price, image_url, is_temporary, duration_days, show_duration,
         requires_text, text_label, notify_admin)
    )
    item_id = c.lastrowid
    conn.commit()
    conn.close()
    return item_id

def db_remove_shop_item(item_id: int, guild_id: int):
    conn = get_db()
    conn.execute("DELETE FROM shop_items WHERE id=? AND guild_id=?", (item_id, guild_id))
    conn.commit()
    conn.close()

def db_update_shop_image(item_id: int, guild_id: int, image_url: str | None):
    conn = get_db()
    conn.execute("UPDATE shop_items SET image_url=? WHERE id=? AND guild_id=?",
                 (image_url, item_id, guild_id))
    conn.commit()
    conn.close()

def db_get_inventory(guild_id: int, user_id: int) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM inventory WHERE guild_id=? AND user_id=? ORDER BY purchased_at DESC",
        (guild_id, user_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_add_inventory(guild_id: int, user_id: int, item_name: str,
                     expires_at: str = None, item_text: str = None):
    conn = get_db()
    conn.execute(
        "INSERT INTO inventory (guild_id, user_id, item_name, purchased_at, expires_at, item_text) VALUES (?,?,?,?,?,?)",
        (guild_id, user_id, item_name, datetime.now().isoformat(), expires_at, item_text)
    )
    conn.commit()
    conn.close()

# ── Reaction helpers ───────────────────────────────────────────

def db_reaction_cooldown_ok(guild_id: int, user_id: int, cooldown_hours: int) -> tuple:
    conn = get_db()
    row = conn.execute("SELECT last_reaction FROM reaction_cooldowns WHERE guild_id=? AND user_id=?",
                       (guild_id, user_id)).fetchone()
    conn.close()
    if not row:
        return True, 0
    last = datetime.fromisoformat(row["last_reaction"])
    elapsed = datetime.now() - last
    if elapsed >= timedelta(hours=cooldown_hours):
        return True, 0
    remaining = timedelta(hours=cooldown_hours) - elapsed
    return False, int(remaining.total_seconds() // 60)

def db_set_reaction_cooldown(guild_id: int, user_id: int):
    conn = get_db()
    now = datetime.now().isoformat()
    conn.execute("""INSERT INTO reaction_cooldowns (guild_id, user_id, last_reaction) VALUES (?,?,?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET last_reaction=?""",
                 (guild_id, user_id, now, now))
    conn.commit()
    conn.close()

def db_get_reaction_msg(guild_id: int, message_id: int) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM reaction_messages WHERE guild_id=? AND message_id=?",
                       (guild_id, message_id)).fetchone()
    conn.close()
    return dict(row) if row else None

def db_add_reaction_msg(guild_id: int, message_id: int, target_uid: int, given_by: int, amount: int):
    conn = get_db()
    conn.execute("""INSERT OR IGNORE INTO reaction_messages
                    (guild_id, message_id, target_uid, given_by_uid, amount, given_at)
                    VALUES (?,?,?,?,?,?)""",
                 (guild_id, message_id, target_uid, given_by, amount, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def db_remove_reaction_msg(guild_id: int, message_id: int):
    conn = get_db()
    conn.execute("DELETE FROM reaction_messages WHERE guild_id=? AND message_id=?", (guild_id, message_id))
    conn.commit()
    conn.close()

# ── Streak helpers ─────────────────────────────────────────────

def db_get_streak(guild_id: int, user_id: int) -> dict:
    conn = get_db()
    row = conn.execute("SELECT * FROM streaks WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
    conn.close()
    return dict(row) if row else {"current_streak": 0, "max_streak": 0, "last_video_id": None}

def db_update_streak(guild_id: int, user_id: int, current_streak: int, last_video_id: str):
    conn = get_db()
    row = conn.execute("SELECT max_streak FROM streaks WHERE guild_id=? AND user_id=?",
                       (guild_id, user_id)).fetchone()
    max_streak = max(row["max_streak"] if row else 0, current_streak)
    conn.execute("""INSERT INTO streaks (guild_id, user_id, current_streak, max_streak, last_video_id)
                    VALUES (?,?,?,?,?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    current_streak=?, max_streak=?, last_video_id=?""",
                 (guild_id, user_id, current_streak, max_streak, last_video_id,
                  current_streak, max_streak, last_video_id))
    conn.commit()
    conn.close()
    return max_streak

# ── User stats helpers ─────────────────────────────────────────

def db_get_stats(guild_id: int, user_id: int) -> dict:
    conn = get_db()
    row = conn.execute("SELECT * FROM user_stats WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
    conn.close()
    return dict(row) if row else {
        "total_shares": 0, "total_invites": 0, "total_boosts": 0,
        "total_quests_done": 0, "max_streak_ever": 0
    }

def db_increment_stat(guild_id: int, user_id: int, column: str, amount: int = 1):
    conn = get_db()
    conn.execute("""INSERT INTO user_stats (guild_id, user_id) VALUES (?,?)
                    ON CONFLICT(guild_id, user_id) DO NOTHING""", (guild_id, user_id))
    conn.execute(f"UPDATE user_stats SET {column} = {column} + ? WHERE guild_id=? AND user_id=?",
                 (amount, guild_id, user_id))
    conn.commit()
    conn.close()

def db_update_max_streak_stat(guild_id: int, user_id: int, streak: int):
    conn = get_db()
    conn.execute("""INSERT INTO user_stats (guild_id, user_id, max_streak_ever) VALUES (?,?,?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET max_streak_ever=MAX(max_streak_ever, ?)""",
                 (guild_id, user_id, streak, streak))
    conn.commit()
    conn.close()

# ── Monthly quest helpers ──────────────────────────────────────

def current_month_key() -> str:
    return datetime.now().strftime("%Y-%m")

def db_get_user_quests(guild_id: int, user_id: int, month_key: str) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM monthly_quests WHERE guild_id=? AND user_id=? AND month_key=?",
        (guild_id, user_id, month_key)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_is_quest_key_enabled(guild_id: int, quest_key: str) -> bool:
    conn = get_db()
    row = conn.execute("SELECT enabled FROM quest_pool_config WHERE guild_id=? AND quest_key=?",
                       (guild_id, quest_key)).fetchone()
    conn.close()
    return (row["enabled"] != 0) if row else True  # default enabled

def db_assign_monthly_quests(guild_id: int, user_id: int, month_key: str):
    """Assign one quest per rarity for this user/month (skip if already assigned).
    Diamond is ALWAYS the "Complete all 4 monthly quests" quest when enabled —
    this guarantees the chain quest is always present.
    Other rarities get a random quest from their pool."""
    existing = db_get_user_quests(guild_id, user_id, month_key)
    existing_rarities = {q["rarity"] for q in existing}
    conn = get_db()
    for rarity in RARITIES:
        if rarity in existing_rarities:
            continue
        if rarity == "diamond":
            # Diamond is always the "all_quests" quest when enabled
            all_q = next((q for q in QUEST_POOL["diamond"] if q["key"] == "all_quests"), None)
            if all_q and db_is_quest_key_enabled(guild_id, "all_quests"):
                quest = all_q
            else:
                # Fallback: any other diamond quest
                pool = [q for q in QUEST_POOL["diamond"] if q["key"] != "all_quests"
                        and db_is_quest_key_enabled(guild_id, q["key"])]
                if not pool:
                    pool = [q for q in QUEST_POOL["diamond"] if q["key"] != "all_quests"]
                if not pool:
                    pool = QUEST_POOL["diamond"]
                quest = random.choice(pool)
        else:
            pool = [q for q in QUEST_POOL[rarity] if db_is_quest_key_enabled(guild_id, q["key"])]
            if not pool:
                pool = QUEST_POOL[rarity]  # fallback: use all if all disabled
            quest = random.choice(pool)
        conn.execute(
            """INSERT OR IGNORE INTO monthly_quests
               (guild_id, user_id, month_key, rarity, quest_key, quest_type, quest_target, quest_name)
               VALUES (?,?,?,?,?,?,?,?)""",
            (guild_id, user_id, month_key, rarity, quest["key"],
             quest["type"], quest["target"], quest["name"])
        )
    conn.commit()
    conn.close()

def db_update_quest_progress(guild_id: int, user_id: int, quest_type: str,
                              amount: int = 1, value: int = None) -> list:
    """
    Update quest progress for all active quests matching quest_type.
    value: for streak quests — set if current value > progress.
    Returns list of newly completed quest dicts.
    """
    month_key = current_month_key()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM monthly_quests WHERE guild_id=? AND user_id=? AND month_key=? AND quest_type=? AND completed=0",
        (guild_id, user_id, month_key, quest_type)
    ).fetchall()
    newly_done = []
    for row in rows:
        quest = dict(row)
        if value is not None:
            new_prog = max(quest["progress"], value)
        else:
            new_prog = quest["progress"] + amount
        completed = 1 if new_prog >= quest["quest_target"] else 0
        conn.execute(
            "UPDATE monthly_quests SET progress=?, completed=? WHERE guild_id=? AND user_id=? AND month_key=? AND rarity=?",
            (new_prog, completed, guild_id, user_id, month_key, quest["rarity"])
        )
        if completed and not quest["completed"]:
            newly_done.append(quest)
    conn.commit()
    conn.close()
    return newly_done

def db_get_all_quests_completed(guild_id: int, user_id: int, month_key: str,
                                 exclude_rarity: str = "diamond") -> bool:
    conn = get_db()
    rows = conn.execute(
        "SELECT completed FROM monthly_quests WHERE guild_id=? AND user_id=? AND month_key=? AND rarity != ?",
        (guild_id, user_id, month_key, exclude_rarity)
    ).fetchall()
    conn.close()
    if not rows:
        return False
    return all(r["completed"] for r in rows)

# ── Achievement helpers ────────────────────────────────────────

def db_get_achievement_config(guild_id: int, achievement_key: str) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM achievement_config WHERE guild_id=? AND achievement_key=? ORDER BY tier",
        (guild_id, achievement_key)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_has_achievement(guild_id: int, user_id: int, achievement_key: str, tier: int) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM achievements WHERE guild_id=? AND user_id=? AND achievement_key=? AND tier=?",
        (guild_id, user_id, achievement_key, tier)
    ).fetchone()
    conn.close()
    return row is not None

def db_unlock_achievement(guild_id: int, user_id: int, achievement_key: str, tier: int):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO achievements (guild_id, user_id, achievement_key, tier, unlocked_at) VALUES (?,?,?,?,?)",
        (guild_id, user_id, achievement_key, tier, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def db_ensure_achievement_config(guild_id: int):
    """Insert default achievement config rows for this guild if missing."""
    conn = get_db()
    for ach in ACHIEVEMENT_DEFS:
        for i, threshold in enumerate(ach["tiers"]):
            conn.execute(
                "INSERT OR IGNORE INTO achievement_config (guild_id, achievement_key, tier, threshold) VALUES (?,?,?,?)",
                (guild_id, ach["key"], i, threshold)
            )
    conn.commit()
    conn.close()

# ── Event helpers ──────────────────────────────────────────────

def db_get_active_events(guild_id: int) -> list:
    now = datetime.now().isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM events WHERE guild_id=? AND enabled=1 AND start_date<=? AND end_date>=?",
        (guild_id, now, now)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_all_events(guild_id: int) -> list:
    conn = get_db()
    rows = conn.execute("SELECT * FROM events WHERE guild_id=? ORDER BY start_date DESC", (guild_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_has_double_xp(guild_id: int) -> float:
    """Returns multiplier (1.0 = no event, 2.0 = double XP)."""
    active = db_get_active_events(guild_id)
    for ev in active:
        if ev["event_type"] == "double_xp":
            try:
                cfg = json.loads(ev["config_json"] or "{}")
                return float(cfg.get("multiplier", 2.0))
            except Exception:
                return 2.0
    return 1.0

def db_get_community_goals(guild_id: int, event_id: int = None) -> list:
    conn = get_db()
    if event_id:
        rows = conn.execute("SELECT * FROM community_goals WHERE guild_id=? AND event_id=? AND enabled=1",
                            (guild_id, event_id)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM community_goals WHERE guild_id=? AND enabled=1", (guild_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_add_goal_contribution(guild_id: int, goal_id: int, user_id: int, amount: int = 1) -> dict:
    """Add user contribution to a community goal. Returns updated goal."""
    conn = get_db()
    row = conn.execute("SELECT * FROM community_goals WHERE id=? AND guild_id=?", (goal_id, guild_id)).fetchone()
    if not row:
        conn.close()
        return {}
    goal = dict(row)
    contribs = json.loads(goal["contributors"] or "[]")
    if user_id not in contribs:
        contribs.append(user_id)
    new_current = goal["current"] + amount
    completed = 1 if new_current >= goal["target"] and not goal["completed"] else goal["completed"]
    conn.execute(
        "UPDATE community_goals SET current=?, contributors=?, completed=? WHERE id=?",
        (new_current, json.dumps(contribs), completed, goal_id)
    )
    conn.commit()
    goal["current"] = new_current
    goal["contributors"] = contribs
    goal["completed"] = completed
    conn.close()
    return goal

# ── Invite cache helpers ───────────────────────────────────────

def db_cache_invites(guild_id: int, invites: list):
    conn = get_db()
    for inv in invites:
        conn.execute(
            "INSERT INTO invites_cache (guild_id, invite_code, inviter_id, uses) VALUES (?,?,?,?) "
            "ON CONFLICT(guild_id, invite_code) DO UPDATE SET uses=?, inviter_id=?",
            (guild_id, inv.code, inv.inviter.id if inv.inviter else 0, inv.uses,
             inv.uses, inv.inviter.id if inv.inviter else 0)
        )
    conn.commit()
    conn.close()

def db_find_used_invite(guild_id: int, current_invites: list) -> Optional[int]:
    """Compare current invite uses to cached to find which invite was used. Returns inviter_id."""
    conn = get_db()
    for inv in current_invites:
        row = conn.execute(
            "SELECT uses, inviter_id FROM invites_cache WHERE guild_id=? AND invite_code=?",
            (guild_id, inv.code)
        ).fetchone()
        if row and inv.uses > row["uses"]:
            inviter_id = row["inviter_id"]
            conn.close()
            return inviter_id if inviter_id else None
    conn.close()
    return None

# ── Backup / Restore ───────────────────────────────────────────

def _registry_update(guild_id: int, channel_id: int):
    try:
        data: dict = {}
        if os.path.exists(BACKUP_REGISTRY):
            with open(BACKUP_REGISTRY, "r") as f:
                data = json.load(f)
        data[str(guild_id)] = channel_id
        with open(BACKUP_REGISTRY, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[Registry] Could not update: {e}")


def _rebuild_registry_from_db():
    """Reconstruct backup_channels.json from the restored DB.
    Called right after a successful restore so the next restart can find
    the backup channel without doing a full guild scan again."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT guild_id, backup_channel_id FROM guild_config "
            "WHERE backup_channel_id IS NOT NULL"
        ).fetchall()
        conn.close()
        data = {str(r["guild_id"]): r["backup_channel_id"] for r in rows}
        if data:
            with open(BACKUP_REGISTRY, "w") as f:
                json.dump(data, f)
            print(f"[Restore] Registry rebuilt with {len(data)} guild(s).")
    except Exception as e:
        print(f"[Restore] Could not rebuild registry: {e}")


async def restore_from_discord(bot: commands.Bot):
    """Restore the DB from the most recent Discord backup.

    Render (and similar platforms) wipe the filesystem on every deploy, so
    backup_channels.json is gone after each restart.  When the registry is
    missing we fall back to scanning every guild's text channels for a .db
    attachment sent by the bot — this is the self-healing path.  After a
    successful restore we immediately rebuild the registry from the restored
    DB so subsequent restarts skip the slow scan.
    """
    registry: dict = {}

    # ── Fast path: registry file still exists (in-session restart) ──
    if os.path.exists(BACKUP_REGISTRY):
        try:
            with open(BACKUP_REGISTRY, "r") as f:
                registry = json.load(f)
            print("[Restore] Registry loaded from file.")
        except Exception as e:
            print(f"[Restore] Could not read registry: {e}")

    # ── Slow path: registry lost (Render cold-start / redeploy) ─────
    if not registry:
        print("[Restore] Registry missing — scanning guilds for backup files (Render recovery)...")
        for guild in bot.guilds:
            found_ch = None
            for channel in guild.text_channels:
                if found_ch:
                    break
                try:
                    async for msg in channel.history(limit=20):
                        if msg.author.id == bot.user.id:
                            for att in msg.attachments:
                                if att.filename.endswith(".db"):
                                    found_ch = channel.id
                                    print(f"[Restore] Found backup in #{channel.name} ({guild.name})")
                                    break
                        if found_ch:
                            break
                except Exception:
                    continue
            if found_ch:
                registry[str(guild.id)] = found_ch

    if not registry:
        print("[Restore] No .db backup found anywhere — starting fresh.")
        return

    # ── Find the most recent .db attachment across all backup channels ─
    best_message = None
    best_ts = None
    for guild_id_str, ch_id in registry.items():
        ch = bot.get_channel(int(ch_id))
        if not ch:
            continue
        try:
            async for msg in ch.history(limit=50):
                for att in msg.attachments:
                    if att.filename.endswith(".db"):
                        if best_ts is None or msg.created_at > best_ts:
                            best_message = msg
                            best_ts = msg.created_at
                        break
        except Exception as e:
            print(f"[Restore] Error reading channel {ch_id}: {e}")

    if not best_message:
        print("[Restore] No .db backup found — starting fresh.")
        return

    att = next(a for a in best_message.attachments if a.filename.endswith(".db"))
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(att.url) as resp:
                if resp.status != 200:
                    print(f"[Restore] Download failed — HTTP {resp.status}")
                    return
                data = await resp.read()
        with open("restore_tmp.db", "wb") as f:
            f.write(data)
        shutil.move("restore_tmp.db", DB_PATH)
        print(f"[Restore] ✅ Restored from {best_ts.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        # Immediately rebuild the registry so the next restart is fast
        _rebuild_registry_from_db()
    except Exception as e:
        print(f"[Restore] Error downloading backup: {e}")

async def do_backup(bot: commands.Bot, guild_id: int):
    config = db_get_config(guild_id)
    ch_id = config.get("backup_channel_id")
    if not ch_id:
        return
    ch = bot.get_channel(ch_id)
    if not ch:
        return
    backup_path = f"backup_{guild_id}.db"
    shutil.copy2(DB_PATH, backup_path)
    try:
        await ch.send(
            f"💾 **Automatic backup** — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            file=discord.File(backup_path)
        )
        _registry_update(guild_id, ch_id)
    except Exception as e:
        print(f"[Backup] {e}")
    finally:
        try:
            os.remove(backup_path)
        except Exception:
            pass

# ══════════════════════════════════════════════════════════════
#  YOUTUBE
# ══════════════════════════════════════════════════════════════

YT_ID_RE = re.compile(
    r'(?:youtube\.com/(?:shorts/|watch\?(?:.*&)?v=)|youtu\.be/)([a-zA-Z0-9_-]{11})'
)

def extract_video_id(text: str) -> Optional[str]:
    m = YT_ID_RE.search(text)
    return m.group(1) if m else None

def make_shorts_url(video_id: str) -> str:
    return f"https://youtube.com/shorts/{video_id}"

def make_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"

async def resolve_youtube_channel_id(handle_or_id: str) -> Optional[str]:
    cleaned = handle_or_id.strip()
    if re.match(r'^UC[a-zA-Z0-9_-]{22}$', cleaned):
        return cleaned
    handle = cleaned.lstrip('@')
    url = f"https://www.youtube.com/@{handle}"
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
                for pattern in [r'"channelId"\s*:\s*"(UC[a-zA-Z0-9_-]{22})"',
                                 r'"externalChannelId"\s*:\s*"(UC[a-zA-Z0-9_-]{22})"']:
                    m = re.search(pattern, html)
                    if m:
                        return m.group(1)
    except Exception as e:
        print(f"[YouTube] Resolve failed for {handle}: {e}")
    return None

async def fetch_latest_videos(channel_id: str) -> list:
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(feed_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
        root = ET.fromstring(text)
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
        videos = []
        for entry in root.findall('atom:entry', ns):
            vid_el   = entry.find('yt:videoId', ns)
            title_el = entry.find('atom:title', ns)
            link_el  = entry.find('atom:link', ns)
            pub_el   = entry.find('atom:published', ns)
            if vid_el is None:
                continue
            vid = vid_el.text
            videos.append({
                'video_id': vid,
                'title':    title_el.text if title_el is not None else 'Video',
                'url':      link_el.get('href', make_watch_url(vid)) if link_el is not None else make_watch_url(vid),
                'published':pub_el.text if pub_el is not None else '',
            })
        return videos
    except Exception as e:
        print(f"[YouTube] RSS fetch error for {channel_id}: {e}")
        return []

# ══════════════════════════════════════════════════════════════
#  PERMISSIONS
# ══════════════════════════════════════════════════════════════

def is_xp_manager(member: discord.Member, config: dict) -> bool:
    role_id = config.get("manager_role_id")
    if not role_id:
        return member.guild_permissions.administrator
    return any(r.id == role_id for r in member.roles)

def in_commands_channel(interaction: discord.Interaction, config: dict) -> bool:
    ch_id = config.get("commands_channel_id")
    if not ch_id:
        return True  # no restriction if not configured
    return interaction.channel_id == ch_id

# ══════════════════════════════════════════════════════════════
#  EMBED HELPERS
# ══════════════════════════════════════════════════════════════

def E(title: str = "", description: str = "", color: int = C_MAIN) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    e.timestamp = datetime.now()
    return e

def _ch(v) -> str:  return f"<#{v}>" if v else "`Not set`"
def _role(v) -> str: return f"<@&{v}>" if v else "`Not set`"
def _val(v, suffix: str = "") -> str: return f"**{v}{suffix}**" if v is not None else "`Not set`"
def _bool(v) -> str: return "✅ Enabled" if v else "❌ Disabled"

def parse_channel_id(value: str) -> Optional[int]:
    m = re.search(r'<#(\d+)>', value) or re.search(r'(\d+)', value)
    return int(m.group(1)) if m else None

def parse_user_id(value: str) -> Optional[int]:
    m = re.search(r'<@!?(\d+)>', value) or re.search(r'^(\d{17,20})$', value.strip())
    return int(m.group(1)) if m else None

def parse_role_id(value: str) -> Optional[int]:
    m = re.search(r'<@&(\d+)>', value) or re.search(r'^(\d{17,20})$', value.strip())
    return int(m.group(1)) if m else None

async def send_log(bot: commands.Bot, guild_id: int, actor: discord.Member, action: str, details: str = ""):
    config = db_get_config(guild_id)
    ch_id = config.get("log_channel_id")
    if not ch_id:
        return
    ch = bot.get_channel(ch_id)
    if not ch:
        return
    e = E(color=C_MAIN)
    e.set_author(name=str(actor), icon_url=actor.display_avatar.url if actor.display_avatar else None)
    e.add_field(name="Action", value=action, inline=False)
    if details:
        e.add_field(name="Details", value=details, inline=False)
    try:
        await ch.send(embed=e)
    except Exception:
        pass

async def notify_admin(bot: commands.Bot, guild_id: int, content: str = "", embed: discord.Embed = None):
    config = db_get_config(guild_id)
    ch_id = config.get("admin_channel_id")
    if not ch_id:
        return
    ch = bot.get_channel(ch_id)
    if not ch:
        return
    try:
        await ch.send(content=content, embed=embed)
    except Exception:
        pass

async def notify_xp(bot: commands.Bot, guild_id: int, content: str = "", embed: discord.Embed = None):
    config = db_get_config(guild_id)
    ch_id = config.get("notification_channel_id")
    if not ch_id:
        return
    ch = bot.get_channel(ch_id)
    if not ch:
        return
    try:
        await ch.send(content=content, embed=embed)
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════
#  STREAK NICKNAME
# ══════════════════════════════════════════════════════════════

async def update_streak_nickname(guild: discord.Guild, user_id: int, streak: int):
    """
    Update member nickname to show streak: "Username 🔥N"
    Requires bot role above member + Manage Nicknames permission.
    Cannot change the server owner's nickname (Discord limitation).
    """
    member = guild.get_member(user_id)
    if not member:
        return
    # Discord never allows bots to change the server owner's nickname
    if member.id == guild.owner_id:
        return
    base_name = member.display_name
    # Remove existing streak suffix
    base_name = re.sub(r'\s*🔥\d+$', '', base_name).strip()
    if streak > 0:
        new_name = f"{base_name} 🔥{streak}"
    else:
        new_name = base_name
    if new_name == member.display_name:
        return
    try:
        await member.edit(nick=new_name[:32])
    except discord.Forbidden:
        print(f"[Streak] ⚠️  Cannot update nickname for {member} ({user_id}): "
              f"bot role must be ABOVE the member's highest role and have Manage Nicknames. "
              f"Check role hierarchy in Server Settings → Roles.")
    except discord.HTTPException as e:
        print(f"[Streak] Nick update error for {user_id}: {e}")

# ══════════════════════════════════════════════════════════════
#  QUEST & ACHIEVEMENT PROCESSING
# ══════════════════════════════════════════════════════════════

async def process_quest_completions(bot: commands.Bot, guild_id: int, user_id: int,
                                    newly_done: list):
    """Award XP and announce newly completed quests."""
    if not newly_done:
        return
    config = db_get_config(guild_id)
    xp_map = {
        "stone": config.get("quest_xp_stone", 50),
        "bronze": config.get("quest_xp_bronze", 100),
        "silver": config.get("quest_xp_silver", 200),
        "gold": config.get("quest_xp_gold", 400),
        "diamond": config.get("quest_xp_diamond", 750),
    }
    guild = bot.get_guild(guild_id)
    member = guild.get_member(user_id) if guild else None
    for quest in newly_done:
        rarity = quest["rarity"]
        xp_reward = xp_map.get(rarity, 50)
        # Mark as awarded
        conn = get_db()
        conn.execute(
            "UPDATE monthly_quests SET xp_awarded=? WHERE guild_id=? AND user_id=? AND month_key=? AND rarity=?",
            (xp_reward, guild_id, user_id, quest["month_key"], rarity)
        )
        conn.commit()
        conn.close()
        db_add_xp(guild_id, user_id, xp_reward)
        db_increment_stat(guild_id, user_id, "total_quests_done")
        # Check all_quests (diamond dependency) — increment by 1 per completed non-diamond quest
        if quest["quest_type"] != "all_quests" and rarity != "diamond":
            diamond_done = db_update_quest_progress(guild_id, user_id, "all_quests", amount=1)
            if diamond_done:
                newly_done.extend(diamond_done)
        # Announce
        e = E(
            f"{RARITY_EMOJI[rarity]} Quest Completed!",
            f"**{quest['quest_name']}**\nReward: **+{xp_reward} XP**",
            RARITY_COLOR[rarity]
        )
        if member:
            e.set_author(name=str(member), icon_url=member.display_avatar.url if member.display_avatar else None)
        await notify_xp(bot, guild_id, embed=e)
        # Check achievements after quest completion
        await check_achievements(bot, guild_id, user_id)

async def check_achievements(bot: commands.Bot, guild_id: int, user_id: int):
    """Check and unlock achievements based on current stats."""
    db_ensure_achievement_config(guild_id)
    stats = db_get_stats(guild_id, user_id)
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    member = guild.get_member(user_id)
    config = db_get_config(guild_id)
    ach_ch_id = config.get("achievement_channel_id")

    for ach_def in ACHIEVEMENT_DEFS:
        key = ach_def["key"]
        stat_val = stats.get(ach_def["category"], 0)
        tiers = db_get_achievement_config(guild_id, key)
        if not tiers:
            # Use defaults
            for i, threshold in enumerate(ach_def["tiers"]):
                tiers.append({"tier": i, "threshold": threshold, "role_id": None, "enabled": 1})

        for tier_row in tiers:
            if not tier_row.get("enabled", 1):
                continue
            tier = tier_row["tier"]
            threshold = tier_row["threshold"]
            role_id = tier_row.get("role_id")
            if stat_val >= threshold and not db_has_achievement(guild_id, user_id, key, tier):
                db_unlock_achievement(guild_id, user_id, key, tier)
                tier_names = ["I", "II", "III", "IV", "V"]
                tier_label = tier_names[tier] if tier < len(tier_names) else str(tier)
                e = E(
                    f"🏆 Achievement Unlocked!",
                    f"**{ach_def['name']} {tier_label}**\n_{threshold}+ {ach_def['category'].replace('_',' ')}_",
                    C_ACHIEVE
                )
                if member:
                    e.set_author(name=str(member), icon_url=member.display_avatar.url if member.display_avatar else None)
                    if role_id:
                        role = guild.get_role(role_id)
                        if role:
                            try:
                                await member.add_roles(role, reason="Achievement unlocked")
                                e.add_field(name="Role awarded", value=f"<@&{role_id}>", inline=False)
                            except Exception:
                                pass
                # Announce in achievement channel
                if ach_ch_id:
                    ch = bot.get_channel(ach_ch_id)
                    if ch:
                        try:
                            await ch.send(
                                content=f"🏆 {member.mention if member else f'<@{user_id}>'}" ,
                                embed=e
                            )
                        except Exception:
                            pass

async def announce_video(bot: commands.Bot, guild_id: int, video_id: str, video_url: str, video_title: str):
    config = db_get_config(guild_id)
    share_id   = config.get("share_channel_id")
    ping_role  = config.get("share_ping_role_id")
    window_min = config.get("share_window_min") or 20
    if not share_id:
        return
    ch = bot.get_channel(share_id)
    if not ch:
        return
    deadline_ts = int((datetime.utcnow() + timedelta(minutes=window_min)).timestamp())
    # Store deadline so streak reminder can use it
    conn = get_db()
    conn.execute("UPDATE current_video SET deadline_ts=? WHERE guild_id=?", (deadline_ts, guild_id))
    conn.commit()
    conn.close()
    role_mention = f"<@&{ping_role}>" if ping_role else "@everyone"
    shorts_url = make_shorts_url(video_id)
    watch_url  = make_watch_url(video_id)
    try:
        await ch.send(
            f"{role_mention} You have **{window_min} minutes** "
            f"(<t:{deadline_ts}:R> — <t:{deadline_ts}:T>) to send the link + screenshot!\n"
            f"📲 {shorts_url}  •  🖥️ {watch_url}"
        )
    except Exception as ex:
        print(f"[Announce] Error: {ex}")

# ══════════════════════════════════════════════════════════════
#  MODALS
# ══════════════════════════════════════════════════════════════

class Modal1(discord.ui.Modal):
    def __init__(self, title: str, label: str, placeholder: str = "",
                 default: str = "", required: bool = True, max_length: int = 200, callback=None):
        super().__init__(title=title)
        self._cb = callback
        self.field = discord.ui.TextInput(label=label, placeholder=placeholder,
                                          default=default, required=required, max_length=max_length)
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        if self._cb:
            await self._cb(interaction, self.field.value)
        else:
            await interaction.response.defer()

class Modal2(discord.ui.Modal):
    def __init__(self, title: str, label1: str, ph1: str, label2: str, ph2: str,
                 default1: str = "", default2: str = "", required1: bool = True, required2: bool = True,
                 max1: int = 200, max2: int = 200, callback=None):
        super().__init__(title=title)
        self._cb = callback
        self.f1 = discord.ui.TextInput(label=label1, placeholder=ph1, default=default1, required=required1, max_length=max1)
        self.f2 = discord.ui.TextInput(label=label2, placeholder=ph2, default=default2, required=required2, max_length=max2)
        self.add_item(self.f1)
        self.add_item(self.f2)

    async def on_submit(self, interaction: discord.Interaction):
        if self._cb:
            await self._cb(interaction, self.f1.value, self.f2.value)
        else:
            await interaction.response.defer()

class Modal3(discord.ui.Modal):
    def __init__(self, title: str,
                 label1: str, ph1: str,
                 label2: str, ph2: str,
                 label3: str, ph3: str,
                 default1="", default2="", default3="",
                 required1=True, required2=True, required3=True,
                 callback=None):
        super().__init__(title=title)
        self._cb = callback
        self.f1 = discord.ui.TextInput(label=label1, placeholder=ph1, default=default1, required=required1)
        self.f2 = discord.ui.TextInput(label=label2, placeholder=ph2, default=default2, required=required2)
        self.f3 = discord.ui.TextInput(label=label3, placeholder=ph3, default=default3, required=required3)
        self.add_item(self.f1); self.add_item(self.f2); self.add_item(self.f3)

    async def on_submit(self, interaction: discord.Interaction):
        if self._cb:
            await self._cb(interaction, self.f1.value, self.f2.value, self.f3.value)
        else:
            await interaction.response.defer()

class Modal4Shop(discord.ui.Modal):
    """4-field modal for shop item creation (image is uploaded separately)."""
    def __init__(self, title: str, callback=None):
        super().__init__(title=title)
        self._cb = callback
        self.f_name  = discord.ui.TextInput(label="Item name (emoji welcome)", placeholder="🎮 Custom Role", max_length=80)
        self.f_price = discord.ui.TextInput(label="Price in XP", placeholder="500")
        self.f_temp  = discord.ui.TextInput(label="Duration in days (0 = permanent)", placeholder="0 or 30")
        self.f_text  = discord.ui.TextInput(label="Text field label (empty = none)", placeholder="Your game username", required=False)
        for f in [self.f_name, self.f_price, self.f_temp, self.f_text]:
            self.add_item(f)

    async def on_submit(self, interaction: discord.Interaction):
        if self._cb:
            await self._cb(interaction, self.f_name.value, self.f_price.value,
                           self.f_temp.value, self.f_text.value)
        else:
            await interaction.response.defer()


class Modal5(discord.ui.Modal):
    """5-field modal for shop item creation (name, price, image URL, duration, text label)."""
    def __init__(self, title: str, callback=None):
        super().__init__(title=title)
        self._cb = callback
        self.f_name  = discord.ui.TextInput(label="Item name (emoji welcome)", placeholder="🎮 Custom Role", max_length=80)
        self.f_price = discord.ui.TextInput(label="Price in XP", placeholder="500")
        self.f_image = discord.ui.TextInput(label="Image URL (empty = no image)", placeholder="https://i.imgur.com/...", required=False)
        self.f_temp  = discord.ui.TextInput(label="Duration in days (0 = permanent)", placeholder="0 or 30")
        self.f_text  = discord.ui.TextInput(label="Text field label (empty = none)", placeholder="Your game username", required=False)
        for f in [self.f_name, self.f_price, self.f_image, self.f_temp, self.f_text]:
            self.add_item(f)

    async def on_submit(self, interaction: discord.Interaction):
        if self._cb:
            await self._cb(interaction, self.f_name.value, self.f_price.value,
                           self.f_image.value, self.f_temp.value, self.f_text.value)
        else:
            await interaction.response.defer()


async def _await_image_upload(bot: commands.Bot, interaction: discord.Interaction,
                               item_name: str) -> str | None:
    """
    Sends a prompt in the channel asking the user to upload an image file.
    Returns the Discord CDN URL of the attachment, or None if skipped/timed out.
    The user's message and the prompt are deleted afterward to keep the channel clean.
    """
    image_result: list[str | None] = [None]
    finished = asyncio.Event()

    class SkipView(discord.ui.View):
        @discord.ui.button(label="⏭️ Passer (sans image)", style=discord.ButtonStyle.grey)
        async def skip(self, i: discord.Interaction, b: discord.ui.Button):
            finished.set()
            self.stop()
            await i.response.defer()

    view = SkipView(timeout=65)

    prompt = await interaction.channel.send(
        f"🖼️ **Image pour « {item_name} »**\n"
        f"Envoie ton image ici depuis ton ordi ou téléphone (jpg, png, gif…), "
        f"ou clique **Passer** pour continuer sans image.\n"
        f"*Tu as 60 secondes. Seul toi peux envoyer.*",
        view=view,
    )

    def msg_check(m: discord.Message) -> bool:
        return (
            m.author.id == interaction.user.id
            and m.channel.id == interaction.channel.id
            and bool(m.attachments)
            and any(
                a.content_type and a.content_type.startswith("image/")
                for a in m.attachments
            )
        )

    async def listen():
        try:
            msg = await bot.wait_for("message", check=msg_check, timeout=60)
            img = next(
                (a for a in msg.attachments
                 if a.content_type and a.content_type.startswith("image/")),
                None,
            )
            if img:
                image_result[0] = img.url
            finished.set()
            view.stop()
            try:
                await msg.delete()
            except Exception:
                pass
        except asyncio.TimeoutError:
            finished.set()
            view.stop()

    listener = asyncio.ensure_future(listen())
    await finished.wait()
    listener.cancel()

    try:
        await prompt.delete()
    except Exception:
        pass

    return image_result[0]

# ══════════════════════════════════════════════════════════════
#  CONFIRM VIEW
# ══════════════════════════════════════════════════════════════

class ConfirmView(discord.ui.View):
    def __init__(self, author_id: int, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.value = None
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This isn't your button.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, btn: discord.ui.Button):
        self.value = True; self.stop(); await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, btn: discord.ui.Button):
        self.value = False; self.stop(); await interaction.response.defer()

# ══════════════════════════════════════════════════════════════
#  /config — MAIN MENU
# ══════════════════════════════════════════════════════════════

def config_overview_embed(guild: discord.Guild, config: dict) -> discord.Embed:
    """Lightweight overview shown when /config is first opened."""
    e = discord.Embed(title=f"⚙️ Config — {guild.name}", color=C_MAIN)
    issues = []
    if not config.get("youtube_channel_id"):      issues.append("YouTube channel")
    if not config.get("share_channel_id"):        issues.append("Share channel")
    if not config.get("notification_channel_id"): issues.append("Notification channel")
    if not config.get("commands_channel_id"):     issues.append("Commands channel")
    if not config.get("manager_role_id"):         issues.append("XP Manager role")
    if issues:
        e.add_field(name="⚠️ Incomplete setup", value="\n".join(f"• {i}" for i in issues), inline=False)
    else:
        e.add_field(name="✅ All essential settings configured", value="\u200b", inline=False)
    e.add_field(name="📹 Video / Reaction XP", value=f"**{config.get('reaction_xp', 50)} XP**", inline=True)
    e.add_field(name="📨 Invite XP",           value=f"**{config.get('invite_xp', 25)} XP**",   inline=True)
    e.add_field(name="🔥 Streak",              value="Enabled" if config.get("streak_enabled", 1) else "Disabled", inline=True)
    e.set_footer(text="Select a category below to edit settings | Click 📊 Status for full details")
    return e

def config_status_embed(guild: discord.Guild, config: dict) -> discord.Embed:
    e = E(f"⚙️ Configuration — {guild.name}", color=C_MAIN)
    # ── Channels & roles ──────────────────────────────────────────
    e.add_field(name="📺 YouTube",            value=f"`{config.get('youtube_channel_id') or 'Not set'}`", inline=True)
    e.add_field(name="🔗 Share Channel",      value=_ch(config.get("share_channel_id")),              inline=True)
    e.add_field(name="🔔 Notifications",      value=_ch(config.get("notification_channel_id")),       inline=True)
    e.add_field(name="💬 Commands Channel",   value=_ch(config.get("commands_channel_id")),           inline=True)
    e.add_field(name="🛡️ Admin Channel",     value=_ch(config.get("admin_channel_id")),              inline=True)
    e.add_field(name="👥 XP Manager Role",    value=_role(config.get("manager_role_id")),             inline=True)
    # ── Features ─────────────────────────────────────────────────
    e.add_field(name="✅ Reaction Emoji",     value=config.get("reaction_emoji", "✅"),               inline=True)
    e.add_field(name="🔥 Streak",             value=_bool(config.get("streak_enabled", 1)),           inline=True)
    e.add_field(name="🎉 Boost Quest",        value=_bool(config.get("boost_quest_enabled", 1)),      inline=True)
    # ── DMs & Welcome ─────────────────────────────────────────────
    e.add_field(name="📩 Welcome DM",         value=_bool(config.get("welcome_dm_enabled", 0)),       inline=True)
    e.add_field(name="👋 Server Welcome",     value=_bool(config.get("server_welcome_enabled", 0)),   inline=True)
    e.add_field(name="⚡ Streak Reminder",    value=_bool(config.get("streak_reminder_enabled", 0)),  inline=True)
    dm_role   = _role(config.get("welcome_dm_role_id"))   or "`All members`"
    on_role   = _role(config.get("welcome_dm_on_role_id"))or "`Not set`"
    sw_ch     = _ch(config.get("server_welcome_channel_id")) or "`Not set`"
    info_ch   = _ch(config.get("info_channel_id"))        or "`Not set`"
    e.add_field(name="📌 DM Role Filter",     value=dm_role,  inline=True)
    e.add_field(name="🎭 DM on Role",         value=on_role,  inline=True)
    e.add_field(name="📢 Welcome Channel",    value=sw_ch,    inline=True)
    e.add_field(name="ℹ️ Info Channel",       value=info_ch,  inline=True)
    # ── Status ────────────────────────────────────────────────────
    issues = []
    if not config.get("youtube_channel_id"):      issues.append("YouTube channel")
    if not config.get("share_channel_id"):        issues.append("Share channel")
    if not config.get("notification_channel_id"): issues.append("Notification channel")
    if not config.get("commands_channel_id"):     issues.append("Commands channel")
    if not config.get("manager_role_id"):         issues.append("XP Manager role")
    if issues:
        e.add_field(name="⚠️ Not configured", value="\n".join(f"• {i}" for i in issues), inline=False)
    else:
        e.add_field(name="✅ Status", value="All essential settings configured.", inline=False)
    e.set_footer(text="Select a category below to edit settings")
    return e

def make_info_embed(guild: discord.Guild, config: dict) -> discord.Embed:
    """Dynamic info embed shown in the info channel — values reflect live config."""
    share_ch = config.get("share_channel_id")
    cmd_ch   = config.get("commands_channel_id")
    share_xp = config.get("reaction_xp", 50)  # video share XP = same setting as reaction XP
    react_xp = share_xp
    inv_xp   = config.get("invite_xp", 25)
    boost_xp = config.get("boost_quest_xp", 100)
    streak_on = config.get("streak_enabled", 1)
    streak_bonus = config.get("streak_xp_bonus", 2)
    streak_cap   = config.get("streak_xp_cap", 30)
    q_stone  = config.get("quest_xp_stone", 50)
    q_diamond= config.get("quest_xp_diamond", 750)

    ch_share = f"<#{share_ch}>" if share_ch else "#share-channel"
    ch_cmd   = f"<#{cmd_ch}>"   if cmd_ch   else "#commands-channel"

    e = E("⚡ How the XP System Works", color=C_GOLD)
    e.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

    e.add_field(
        name="🎬 Share a Video",
        value=f"Post the link + a screenshot in {ch_share} within the time window.\n**+{share_xp} XP** per video"
              + (f" — consecutive shares build a 🔥 **Streak** (+{streak_bonus} XP/level, up to +{streak_cap} XP)" if streak_on else ""),
        inline=False
    )
    e.add_field(
        name="✅ Reaction Bonus",
        value=f"An XP Manager reacts to your message → **+{react_xp} XP**",
        inline=True
    )
    e.add_field(
        name="📨 Invite a Friend",
        value=f"Someone joins through your link → **+{inv_xp} XP**",
        inline=True
    )
    e.add_field(
        name="🚀 Server Boost",
        value=f"Boost the server → **+{boost_xp} XP** (repeatable)",
        inline=True
    )
    e.add_field(
        name="📅 Monthly Quests",
        value=f"Complete quests each month to earn between **{q_stone} XP** (Stone) and **{q_diamond} XP** (Diamond).\nUse `/quests` to check your progress.",
        inline=False
    )
    e.add_field(
        name="🛒 What can you do with XP?",
        value="Spend your XP in the `/shop` to unlock **exclusive rewards** — pins, skins, friend requests, and more.\nCheck `/shop` to see what's available right now.",
        inline=False
    )
    e.add_field(
        name="📊 Check your XP",
        value=f"Use `/xp`, `/leaderboard`, `/inventory`, `/achievements` in {ch_cmd}.",
        inline=False
    )
    e.set_footer(text=f"Updated • {datetime.now().strftime('%d %b %Y %H:%M')}")
    return e


async def post_or_update_info_embed(bot: commands.Bot, guild: discord.Guild, config: dict):
    """Post the info embed in the info channel, or edit the existing one."""
    ch_id  = config.get("info_channel_id")
    msg_id = config.get("info_message_id")
    if not ch_id:
        return False, "No info channel configured."
    ch = bot.get_channel(ch_id)
    if not ch:
        return False, "Info channel not found — bot may lack access."
    embed = make_info_embed(guild, config)
    if msg_id:
        try:
            msg = await ch.fetch_message(msg_id)
            await msg.edit(embed=embed)
            return True, "Info message updated ✅"
        except discord.NotFound:
            pass  # Message deleted — post a new one
    try:
        msg = await ch.send(embed=embed)
        db_set_config(guild.id, info_message_id=msg.id)
        return True, "Info message posted ✅"
    except Exception as ex:
        return False, f"Error: {ex}"


async def send_welcome_dm(member: discord.Member, config: dict):
    """Send the welcome DM to a new member."""
    info_ch = config.get("info_channel_id")
    info_str = f"<#{info_ch}>" if info_ch else "the info channel"
    e = discord.Embed(
        title=f"👋 Welcome to **{member.guild.name}**!",
        color=C_MAIN
    )
    e.description = (
        f"Hey **{member.display_name}** — glad to have you here! 🎉\n\n"
        f"I'm **Meeple**, the XP bot for this server. Here's a quick overview:\n\n"
        f"🎬 **Share videos** in the share channel to earn XP\n"
        f"📅 **Complete monthly quests** for bonus rewards\n"
        f"🛒 **Spend your XP** in the `/shop` to unlock exclusive rewards — pins, skins, friend requests, and more\n"
        f"🏆 **Climb the leaderboard** and unlock achievements to earn special roles\n"
        f"🔥 **Build a streak** by sharing every video — the longer your streak, the bigger the bonus\n\n"
        f"Head over to {info_str} to learn exactly how everything works.\n\n"
        f"Good luck, and enjoy the server! 🚀"
    )
    e.set_footer(text=f"{member.guild.name} • XP System")
    try:
        await member.send(embed=e)
    except discord.Forbidden:
        pass  # User has DMs disabled


class ConfigMainMenu(discord.ui.View):
    def __init__(self, guild: discord.Guild, author_id: int):
        super().__init__(timeout=300)
        self.guild = guild
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This panel belongs to someone else.", ephemeral=True)
            return False
        return True

    async def _go(self, interaction, embed, view):
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="📺 YouTube",     style=discord.ButtonStyle.blurple, row=0)
    async def cat_yt(self, i, b):
        sub = ConfigYouTubeMenu(self.guild, self.author_id)
        await self._go(i, sub.build_embed(db_get_config(self.guild.id)), sub)

    @discord.ui.button(label="💬 Channels",    style=discord.ButtonStyle.blurple, row=0)
    async def cat_ch(self, i, b):
        sub = ConfigChannelsMenu(self.guild, self.author_id)
        await self._go(i, sub.build_embed(db_get_config(self.guild.id)), sub)

    @discord.ui.button(label="💰 XP & Invites", style=discord.ButtonStyle.blurple, row=0)
    async def cat_xp(self, i, b):
        sub = ConfigXPMenu(self.guild, self.author_id)
        await self._go(i, sub.build_embed(db_get_config(self.guild.id)), sub)

    @discord.ui.button(label="🔥 Streak",      style=discord.ButtonStyle.blurple, row=0)
    async def cat_streak(self, i, b):
        sub = ConfigStreakMenu(self.guild, self.author_id)
        await self._go(i, sub.build_embed(db_get_config(self.guild.id)), sub)

    @discord.ui.button(label="🛒 Shop",        style=discord.ButtonStyle.blurple, row=0)
    async def cat_shop(self, i, b):
        sub = ConfigShopMenu(self.guild, self.author_id)
        await self._go(i, sub.build_embed(db_get_config(self.guild.id)), sub)

    @discord.ui.button(label="📅 Quests",      style=discord.ButtonStyle.blurple, row=1)
    async def cat_quests(self, i, b):
        sub = ConfigQuestsMenu(self.guild, self.author_id)
        await self._go(i, sub.build_embed(db_get_config(self.guild.id)), sub)

    @discord.ui.button(label="🏆 Achievements", style=discord.ButtonStyle.blurple, row=1)
    async def cat_ach(self, i, b):
        sub = ConfigAchievementsMenu(self.guild, self.author_id)
        await self._go(i, sub.build_embed(db_get_config(self.guild.id)), sub)

    @discord.ui.button(label="🎉 Events",      style=discord.ButtonStyle.blurple, row=1)
    async def cat_events(self, i, b):
        sub = ConfigEventsMenu(self.guild, self.author_id)
        await self._go(i, sub.build_embed(db_get_config(self.guild.id)), sub)

    @discord.ui.button(label="👥 Permissions", style=discord.ButtonStyle.blurple, row=1)
    async def cat_perms(self, i, b):
        sub = ConfigPermissionsMenu(self.guild, self.author_id)
        await self._go(i, sub.build_embed(db_get_config(self.guild.id)), sub)

    @discord.ui.button(label="📊 Status",      style=discord.ButtonStyle.grey, row=1)
    async def cat_status(self, i, b):
        await i.response.edit_message(embed=config_status_embed(self.guild, db_get_config(self.guild.id)), view=self)

    @discord.ui.button(label="📨 DMs & Welcome", style=discord.ButtonStyle.blurple, row=2)
    async def cat_dms(self, i, b):
        sub = ConfigDMsMenu(self.guild, self.author_id)
        await self._go(i, sub.build_embed(db_get_config(self.guild.id)), sub)

# ══════════════════════════════════════════════════════════════
#  SUBMENU BASE
# ══════════════════════════════════════════════════════════════

class _SubMenu(discord.ui.View):
    def __init__(self, guild: discord.Guild, author_id: int):
        super().__init__(timeout=300)
        self.guild = guild
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This panel belongs to someone else.", ephemeral=True)
            return False
        return True

    def build_embed(self, config: dict) -> discord.Embed:
        raise NotImplementedError

    async def _back(self, interaction: discord.Interaction):
        config = db_get_config(self.guild.id)
        main = ConfigMainMenu(self.guild, self.author_id)
        await interaction.response.edit_message(embed=config_status_embed(self.guild, config), view=main)

    async def _refresh(self, interaction: discord.Interaction):
        config = db_get_config(self.guild.id)
        await interaction.edit_original_response(embed=self.build_embed(config), view=self)

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.grey, row=4)
    async def btn_back(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await self._back(interaction)

# ══════════════════════════════════════════════════════════════
#  SUBMENUS
# ══════════════════════════════════════════════════════════════

class ConfigYouTubeMenu(_SubMenu):
    def build_embed(self, config: dict) -> discord.Embed:
        e = E("📺 YouTube Settings", color=C_MAIN)
        e.add_field(name="YouTube Channel ID", value=f"`{config.get('youtube_channel_id') or 'Not set'}`", inline=True)
        e.set_footer(text="The bot checks for new videos every 60 seconds")
        return e

    @discord.ui.button(label="Set YouTube Channel", style=discord.ButtonStyle.blurple, row=0)
    async def btn_yt(self, interaction: discord.Interaction, btn: discord.ui.Button):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            await inter.response.send_message("🔍 Resolving channel...", ephemeral=True)
            ch_id = await resolve_youtube_channel_id(value)
            if not ch_id:
                await inter.edit_original_response(content="❌ Could not find this channel. Check the handle or paste the ID directly.")
                return
            db_set_config(self.guild.id, youtube_channel_id=ch_id)
            await inter.edit_original_response(content=f"✅ YouTube channel set to `{ch_id}`")
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1(
            title="Set YouTube Channel", label="Channel handle or ID",
            placeholder="@YourChannel  or  UCxxxxxxxxxxxxxxxxxxxxxxxxx",
            default=config.get("youtube_channel_id") or "", callback=submit
        ))

    @discord.ui.button(label="Test YouTube Feed", style=discord.ButtonStyle.grey, row=0)
    async def btn_test(self, interaction: discord.Interaction, btn: discord.ui.Button):
        config = db_get_config(self.guild.id)
        ch_id = config.get("youtube_channel_id")
        if not ch_id:
            await interaction.response.send_message("❌ No YouTube channel configured.", ephemeral=True)
            return
        await interaction.response.send_message("🔍 Fetching feed...", ephemeral=True)
        videos = await fetch_latest_videos(ch_id)
        if not videos:
            await interaction.edit_original_response(content="❌ No videos found or invalid channel ID.")
            return
        latest = videos[0]
        await interaction.edit_original_response(
            content=f"✅ Feed working!\n**Latest:** {latest['title']}\n🔗 {latest['url']}"
        )

class ConfigChannelsMenu(_SubMenu):
    def build_embed(self, config: dict) -> discord.Embed:
        e = E("💬 Channel Settings", color=C_MAIN)
        e.add_field(name="🔗 Share Channel",      value=_ch(config.get("share_channel_id")),              inline=True)
        e.add_field(name="🔔 Notifications",      value=_ch(config.get("notification_channel_id")),       inline=True)
        e.add_field(name="💬 Commands",           value=_ch(config.get("commands_channel_id")),           inline=True)
        e.add_field(name="🛡️ Admin",             value=_ch(config.get("admin_channel_id")),              inline=True)
        e.add_field(name="📋 Log",                value=_ch(config.get("log_channel_id")),                inline=True)
        e.add_field(name="💾 Backup",             value=_ch(config.get("backup_channel_id")),             inline=True)
        ping_r = _role(config.get("share_ping_role_id")) if config.get("share_ping_role_id") else "`@everyone`"
        e.add_field(name="🔔 Ping Role",          value=ping_r,                                           inline=True)
        e.add_field(name="\u200b", value=(
            "**Share** — members post link + screenshot here\n"
            "**Notifications** — invites, quests, achievements\n"
            "**Commands** — /xp, /shop, /quests, etc.\n"
            "**Admin** — expired items, text orders\n"
            "**Log** — admin actions\n"
            "**Backup** — DB file every 15 min"
        ), inline=False)
        return e

    def _ch_btn(self, label: str, config_key: str, title: str):
        async def handler(interaction: discord.Interaction, btn):
            config = db_get_config(self.guild.id)
            async def submit(inter, value):
                if not value.strip():
                    db_set_config(self.guild.id, **{config_key: None})
                    await inter.response.send_message("✅ Channel removed.", ephemeral=True)
                    await self._refresh(interaction)
                    return
                ch_id = parse_channel_id(value)
                if not ch_id:
                    await inter.response.send_message("❌ Invalid channel.", ephemeral=True)
                    return
                db_set_config(self.guild.id, **{config_key: ch_id})
                await inter.response.send_message(f"✅ Set to <#{ch_id}>", ephemeral=True)
                await self._refresh(interaction)
            await interaction.response.send_modal(Modal1(
                title=title, label="Channel mention or ID (empty = remove)",
                placeholder="#channel  or  1234567890",
                default=str(config.get(config_key) or ""),
                required=False, callback=submit
            ))
        return handler

    @discord.ui.button(label="Share Channel",        style=discord.ButtonStyle.blurple, row=0)
    async def btn_share(self, interaction, btn):
        await self._ch_btn("Share Channel", "share_channel_id", "Set Share Channel")(interaction, btn)

    @discord.ui.button(label="Notifications",        style=discord.ButtonStyle.blurple, row=0)
    async def btn_notif(self, interaction, btn):
        await self._ch_btn("Notifications", "notification_channel_id", "Set Notification Channel")(interaction, btn)

    @discord.ui.button(label="Commands Channel",     style=discord.ButtonStyle.blurple, row=0)
    async def btn_cmd(self, interaction, btn):
        await self._ch_btn("Commands Channel", "commands_channel_id", "Set Commands Channel")(interaction, btn)

    @discord.ui.button(label="Admin Channel",        style=discord.ButtonStyle.blurple, row=1)
    async def btn_admin(self, interaction, btn):
        await self._ch_btn("Admin Channel", "admin_channel_id", "Set Admin Channel")(interaction, btn)

    @discord.ui.button(label="Log Channel",          style=discord.ButtonStyle.blurple, row=1)
    async def btn_log(self, interaction, btn):
        await self._ch_btn("Log Channel", "log_channel_id", "Set Log Channel")(interaction, btn)

    @discord.ui.button(label="Backup Channel",       style=discord.ButtonStyle.blurple, row=1)
    async def btn_bak(self, interaction, btn):
        await self._ch_btn("Backup Channel", "backup_channel_id", "Set Backup Channel")(interaction, btn)

    @discord.ui.button(label="Ping Role",            style=discord.ButtonStyle.grey, row=2)
    async def btn_ping(self, interaction: discord.Interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            if not value.strip():
                db_set_config(self.guild.id, share_ping_role_id=None)
                await inter.response.send_message("✅ Ping role removed — bot will use @everyone.", ephemeral=True)
                await self._refresh(interaction)
                return
            raw = value.strip().lstrip("<@&").rstrip(">")
            if not raw.isdigit():
                await inter.response.send_message("❌ Mention the role or paste its ID.", ephemeral=True)
                return
            db_set_config(self.guild.id, share_ping_role_id=int(raw))
            await inter.response.send_message(f"✅ Ping role set to <@&{raw}>", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1(
            title="Set Ping Role", label="Role mention or ID (empty = @everyone)",
            placeholder="@Subscribers  or  1234567890",
            default=str(config.get("share_ping_role_id") or ""),
            required=False, callback=submit
        ))

    @discord.ui.button(label="Info Channel",         style=discord.ButtonStyle.blurple, row=2)
    async def btn_info_ch(self, interaction: discord.Interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            if not value.strip():
                db_set_config(self.guild.id, info_channel_id=None, info_message_id=None)
                await inter.response.send_message("✅ Info channel removed.", ephemeral=True)
                await self._refresh(interaction)
                return
            ch_id = parse_channel_id(value)
            if not ch_id:
                await inter.response.send_message("❌ Invalid channel.", ephemeral=True)
                return
            db_set_config(self.guild.id, info_channel_id=ch_id, info_message_id=None)
            await inter.response.send_message(f"✅ Info channel set to <#{ch_id}>\nUse **Update Info Message** to post the embed.", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1(
            title="Set Info Channel", label="Channel mention or ID (empty = remove)",
            placeholder="#xp-info  or  1234567890",
            default=str(config.get("info_channel_id") or ""),
            required=False, callback=submit
        ))

    @discord.ui.button(label="Update Info Message",  style=discord.ButtonStyle.green, row=3)
    async def btn_update_info(self, interaction: discord.Interaction, btn):
        await interaction.response.defer(ephemeral=True)
        config = db_get_config(self.guild.id)
        ok, msg = await post_or_update_info_embed(bot, self.guild, config)
        await interaction.followup.send(f"{'✅' if ok else '❌'} {msg}", ephemeral=True)

class ConfigDMsMenu(_SubMenu):
    def build_embed(self, config: dict) -> discord.Embed:
        e = E("📨 DMs & Welcome Settings", color=C_INFO)
        _on  = lambda v: "✅ Enabled" if v else "❌ Disabled"
        e.add_field(name="📩 Welcome DM (on join)",      value=_on(config.get("welcome_dm_enabled", 0)),       inline=True)
        e.add_field(name="🔖 DM Role Filter",            value=_role(config.get("welcome_dm_role_id")) or "`All new members`", inline=True)
        e.add_field(name="🎭 DM on Role Assign",         value=_role(config.get("welcome_dm_on_role_id")) or "`Not set`",      inline=True)
        e.add_field(name="👋 Server Welcome Msg",        value=_on(config.get("server_welcome_enabled", 0)),   inline=True)
        e.add_field(name="📢 Welcome Channel",           value=_ch(config.get("server_welcome_channel_id")),   inline=True)
        e.add_field(name="🎭 Welcome on Role Assign",    value=_role(config.get("server_welcome_on_role_id")) or "`Not set`",  inline=True)
        e.add_field(name="⚠️ Streak Reminder DM",       value=_on(config.get("streak_reminder_enabled", 0)),  inline=True)
        e.add_field(name="\u200b", value=(
            "**Welcome DM** — bot DMs new members when they join\n"
            "**DM Role Filter** — only DM members who already have this role (optional)\n"
            "**DM on Role Assign** — also DM when a member receives this specific role\n"
            "**Server Welcome Msg** — posts a welcome message in a channel\n"
            "**Welcome on Role Assign** — triggers welcome msg when member gets this role\n"
            "**Streak Reminder** — DMs members with <5 min left to share and keep their streak"
        ), inline=False)
        return e

    def _parse_role(self, value: str):
        raw = value.strip().lstrip("<@&").rstrip(">")
        return int(raw) if raw.isdigit() else None

    @discord.ui.button(label="Toggle Welcome DM",        style=discord.ButtonStyle.blurple, row=0)
    async def btn_toggle_dm(self, interaction: discord.Interaction, btn):
        config = db_get_config(self.guild.id)
        new_val = 0 if config.get("welcome_dm_enabled", 0) else 1
        db_set_config(self.guild.id, welcome_dm_enabled=new_val)
        await interaction.response.send_message(
            f"✅ Welcome DM {'**enabled**' if new_val else '**disabled**'}.", ephemeral=True)
        await self._refresh(interaction)

    @discord.ui.button(label="DM Role Filter",           style=discord.ButtonStyle.grey,    row=0)
    async def btn_dm_role(self, interaction: discord.Interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            if not value.strip():
                db_set_config(self.guild.id, welcome_dm_role_id=None)
                await inter.response.send_message("✅ Role filter removed — all new members will be DM'd.", ephemeral=True)
            else:
                rid = self._parse_role(value)
                if not rid:
                    await inter.response.send_message("❌ Invalid role.", ephemeral=True); return
                db_set_config(self.guild.id, welcome_dm_role_id=rid)
                await inter.response.send_message(f"✅ Only members with <@&{rid}> will receive the DM.", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1(
            title="DM Role Filter", label="Role mention or ID (empty = all members)",
            placeholder="@Member  or  1234567890",
            default=str(config.get("welcome_dm_role_id") or ""),
            required=False, callback=submit
        ))

    @discord.ui.button(label="DM on Role Assign",        style=discord.ButtonStyle.grey,    row=0)
    async def btn_dm_on_role(self, interaction: discord.Interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            if not value.strip():
                db_set_config(self.guild.id, welcome_dm_on_role_id=None)
                await inter.response.send_message("✅ Role trigger removed.", ephemeral=True)
            else:
                rid = self._parse_role(value)
                if not rid:
                    await inter.response.send_message("❌ Invalid role.", ephemeral=True); return
                db_set_config(self.guild.id, welcome_dm_on_role_id=rid)
                await inter.response.send_message(f"✅ Bot will DM members when they receive <@&{rid}>.", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1(
            title="DM on Role Assign", label="Role mention or ID (empty = disable)",
            placeholder="@Verified  or  1234567890",
            default=str(config.get("welcome_dm_on_role_id") or ""),
            required=False, callback=submit
        ))

    @discord.ui.button(label="Toggle Welcome Msg",       style=discord.ButtonStyle.blurple, row=1)
    async def btn_toggle_sw(self, interaction: discord.Interaction, btn):
        config = db_get_config(self.guild.id)
        new_val = 0 if config.get("server_welcome_enabled", 0) else 1
        db_set_config(self.guild.id, server_welcome_enabled=new_val)
        await interaction.response.send_message(
            f"✅ Server welcome message {'**enabled**' if new_val else '**disabled**'}.", ephemeral=True)
        await self._refresh(interaction)

    @discord.ui.button(label="Welcome Channel",          style=discord.ButtonStyle.grey,    row=1)
    async def btn_sw_channel(self, interaction: discord.Interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            if not value.strip():
                db_set_config(self.guild.id, server_welcome_channel_id=None)
                await inter.response.send_message("✅ Welcome channel removed.", ephemeral=True)
            else:
                ch_id = parse_channel_id(value)
                if not ch_id:
                    await inter.response.send_message("❌ Invalid channel.", ephemeral=True); return
                db_set_config(self.guild.id, server_welcome_channel_id=ch_id)
                await inter.response.send_message(f"✅ Welcome messages will be posted in <#{ch_id}>.", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1(
            title="Welcome Channel", label="Channel mention or ID (empty = remove)",
            placeholder="#welcome  or  1234567890",
            default=str(config.get("server_welcome_channel_id") or ""),
            required=False, callback=submit
        ))

    @discord.ui.button(label="Welcome on Role Assign",   style=discord.ButtonStyle.grey,    row=1)
    async def btn_sw_on_role(self, interaction: discord.Interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            if not value.strip():
                db_set_config(self.guild.id, server_welcome_on_role_id=None)
                await inter.response.send_message("✅ Role trigger removed.", ephemeral=True)
            else:
                rid = self._parse_role(value)
                if not rid:
                    await inter.response.send_message("❌ Invalid role.", ephemeral=True); return
                db_set_config(self.guild.id, server_welcome_on_role_id=rid)
                await inter.response.send_message(
                    f"✅ Welcome message will post when a member receives <@&{rid}>.", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1(
            title="Welcome on Role Assign", label="Role mention or ID (empty = disable)",
            placeholder="@Verified  or  1234567890",
            default=str(config.get("server_welcome_on_role_id") or ""),
            required=False, callback=submit
        ))

    @discord.ui.button(label="Toggle Streak Reminder",   style=discord.ButtonStyle.blurple, row=2)
    async def btn_toggle_streak_reminder(self, interaction: discord.Interaction, btn):
        config = db_get_config(self.guild.id)
        new_val = 0 if config.get("streak_reminder_enabled", 0) else 1
        db_set_config(self.guild.id, streak_reminder_enabled=new_val)
        await interaction.response.send_message(
            f"✅ Streak reminder DM {'**enabled**' if new_val else '**disabled**'}.\n"
            f"{'Members with an active streak will be DM\'d when < 5 min remain to share.' if new_val else ''}",
            ephemeral=True)
        await self._refresh(interaction)


class ConfigXPMenu(_SubMenu):
    def build_embed(self, config: dict) -> discord.Embed:
        e = E("💰 XP & Invite Settings", color=C_GOLD)
        e.add_field(name="⏰ Share Window",       value=f"**{config.get('share_window_min', 20)} min**", inline=True)
        e.add_field(name="✅ Reaction Emoji",     value=config.get("reaction_emoji", "✅"),              inline=True)
        e.add_field(name="📹 Video / Reaction XP", value=f"**{config.get('reaction_xp', 50)} XP**",       inline=True)
        e.add_field(name="⏱️ Reaction Cooldown", value=f"**{config.get('reaction_cooldown_h', 1)}h**",  inline=True)
        e.add_field(name="📨 Invite XP",           value=f"**{config.get('invite_xp', 25)} XP**",       inline=True)
        e.set_footer(text="📹 Video / Reaction XP is used for both video shares and manager reactions")
        return e

    @discord.ui.button(label="Share Window",     style=discord.ButtonStyle.blurple, row=0)
    async def btn_window(self, interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            try:
                mins = int(value)
                if mins <= 0: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Enter a positive number of minutes.", ephemeral=True)
                return
            db_set_config(self.guild.id, share_window_min=mins)
            await inter.response.send_message(f"✅ Share window set to **{mins} min**", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1("Share Window", "Minutes to share after video",
            placeholder="20", default=str(config.get("share_window_min", 20)), callback=submit))

    @discord.ui.button(label="Reaction Emoji",   style=discord.ButtonStyle.blurple, row=0)
    async def btn_emoji(self, interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            db_set_config(self.guild.id, reaction_emoji=value.strip())
            await inter.response.send_message(f"✅ Reaction emoji set to **{value.strip()}**", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1("Reaction Emoji", "Standard or custom emoji",
            placeholder="✅  or  <:custom:1234567890>",
            default=config.get("reaction_emoji", "✅"), callback=submit))

    @discord.ui.button(label="Video / Reaction XP", style=discord.ButtonStyle.blurple, row=0)
    async def btn_react_xp(self, interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            try:
                amt = int(value)
                if amt <= 0: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Enter a positive number.", ephemeral=True)
                return
            db_set_config(self.guild.id, reaction_xp=amt, share_xp=amt)
            await inter.response.send_message(f"✅ Video share + Reaction XP set to **{amt} XP**", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1("Video / Reaction XP",
            "XP for video shares AND manager reactions (same value)",
            placeholder="50", default=str(config.get("reaction_xp", 50)), callback=submit))

    @discord.ui.button(label="Reaction Cooldown", style=discord.ButtonStyle.grey, row=1)
    async def btn_cooldown(self, interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            try:
                hours = int(value)
                if hours < 0: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Enter hours (0 = no cooldown).", ephemeral=True)
                return
            db_set_config(self.guild.id, reaction_cooldown_h=hours)
            await inter.response.send_message(f"✅ Cooldown set to **{hours}h**", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1("Reaction Cooldown", "Hours between reaction XP (0 = none)",
            placeholder="1", default=str(config.get("reaction_cooldown_h", 1)), callback=submit))

    @discord.ui.button(label="Invite XP",        style=discord.ButtonStyle.grey, row=1)
    async def btn_invite_xp(self, interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            try:
                amt = int(value)
                if amt < 0: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Enter a non-negative number.", ephemeral=True)
                return
            db_set_config(self.guild.id, invite_xp=amt)
            await inter.response.send_message(f"✅ Invite XP set to **{amt} XP**", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1("Invite XP", "XP awarded per successful invite",
            placeholder="25", default=str(config.get("invite_xp", 25)), callback=submit))

class ConfigStreakMenu(_SubMenu):
    def build_embed(self, config: dict) -> discord.Embed:
        e = E("🔥 Streak Settings", color=C_STREAK)
        e.add_field(name="Enabled",           value=_bool(config.get("streak_enabled", 1)),         inline=True)
        e.add_field(name="XP Bonus per Level",value=f"**+{config.get('streak_xp_bonus', 2)} XP**",  inline=True)
        e.add_field(name="XP Bonus Cap",      value=f"**+{config.get('streak_xp_cap', 30)} XP max**",inline=True)
        e.add_field(name="Reset on Miss",     value=_bool(config.get("streak_reset_on_miss", 1)),    inline=True)
        e.add_field(name="\u200b", value=(
            "The streak increases by 1 for each consecutive video supported.\n"
            "**Bonus XP** = min(streak × bonus, cap)  — added on top of share XP.\n"
            "The streak is displayed in the member's nickname: **username 🔥N**\n"
            "⚠️ The bot needs **Manage Nicknames** and must be **above the member** in role hierarchy."
        ), inline=False)
        return e

    @discord.ui.button(label="Toggle Streak",   style=discord.ButtonStyle.blurple, row=0)
    async def btn_toggle(self, interaction, btn):
        config = db_get_config(self.guild.id)
        new_val = 0 if config.get("streak_enabled", 1) else 1
        db_set_config(self.guild.id, streak_enabled=new_val)
        await interaction.response.edit_message(embed=self.build_embed(db_get_config(self.guild.id)), view=self)

    @discord.ui.button(label="XP Bonus per Level", style=discord.ButtonStyle.blurple, row=0)
    async def btn_bonus(self, interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            try:
                amt = int(value)
                if amt < 0: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Enter a non-negative number.", ephemeral=True)
                return
            db_set_config(self.guild.id, streak_xp_bonus=amt)
            await inter.response.send_message(f"✅ Streak bonus set to **+{amt} XP per level**", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1("Streak XP Bonus", "XP added per streak level",
            placeholder="2", default=str(config.get("streak_xp_bonus", 2)), callback=submit))

    @discord.ui.button(label="XP Bonus Cap",    style=discord.ButtonStyle.blurple, row=0)
    async def btn_cap(self, interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            try:
                amt = int(value)
                if amt < 0: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Enter a non-negative number.", ephemeral=True)
                return
            db_set_config(self.guild.id, streak_xp_cap=amt)
            await inter.response.send_message(f"✅ Streak XP cap set to **+{amt} XP**", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1("Streak XP Cap", "Maximum streak bonus XP",
            placeholder="30", default=str(config.get("streak_xp_cap", 30)), callback=submit))

    @discord.ui.button(label="Toggle Reset on Miss", style=discord.ButtonStyle.grey, row=1)
    async def btn_reset(self, interaction, btn):
        config = db_get_config(self.guild.id)
        new_val = 0 if config.get("streak_reset_on_miss", 1) else 1
        db_set_config(self.guild.id, streak_reset_on_miss=new_val)
        await interaction.response.edit_message(embed=self.build_embed(db_get_config(self.guild.id)), view=self)

class ConfigShopMenu(_SubMenu):
    def build_embed(self, config: dict) -> discord.Embed:
        items = db_get_shop_items(self.guild.id)
        e = E("🛒 Shop Settings", color=C_GOLD)
        if not items:
            e.description = "The shop is empty. Add items that members can buy with XP."
        else:
            e.description = f"**{len(items)} item(s)** in the shop.\n\u200b"
            for item in items[:8]:
                tags = []
                if item.get("is_temporary"): tags.append(f"⏳{item['duration_days']}d")
                if item.get("requires_text"): tags.append("📝")
                if item.get("image_url"): tags.append("🖼️")
                tag_str = "  " + " ".join(tags) if tags else ""
                e.add_field(
                    name=f"{item['name']}{tag_str}",
                    value=f"**{item['price']} XP** — ID `{item['id']}`",
                    inline=True
                )
            if len(items) > 8:
                e.add_field(name="…", value=f"and {len(items)-8} more — use 📋 View All", inline=False)
        e.set_footer(text="🖼️ = has image  ⏳ = temporary  📝 = requires text input")
        return e

    @discord.ui.button(label="➕ Add Item", style=discord.ButtonStyle.green, row=0)
    async def btn_add(self, interaction: discord.Interaction, btn):
        guild_ref = self.guild
        parent_interaction = interaction
        async def submit(inter, v_name, v_price, v_temp, v_text):
            try:
                price = int(v_price)
                if price <= 0: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Price must be a positive number.", ephemeral=True)
                return
            try:
                days = int(v_temp)
                if days < 0: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Duration must be 0 (permanent) or a positive number of days.", ephemeral=True)
                return
            is_temp       = 1 if days > 0 else 0
            dur_days      = days if days > 0 else None
            requires_text = 1 if v_text.strip() else 0
            text_label    = v_text.strip() or None
            item_id = db_add_shop_item(guild_ref.id, v_name.strip(), price, None,
                                       is_temp, dur_days, 1, requires_text, text_label)
            tags = []
            if is_temp:        tags.append(f"⏳ {days} days")
            if requires_text:  tags.append(f"📝 requires text")
            await inter.response.send_message(
            await inter.response.send_message(
                "\u2705 Added **" + v_name.strip() + "** \u2014 **" + str(price) + " XP** (ID: `" + str(item_id) + "`)"
                + ("\n" + "  ".join(tags) if tags else "\nPermanent, no text required")
                + "\n\U0001f5bc\ufe0f Now upload an image in this channel, or click **Skip**.",
                ephemeral=True
            )
            )
            # Let the manager upload an image from their device right after creating the item
            img_url = await _await_image_upload(bot, inter, v_name.strip())
            if img_url:
                db_update_shop_image(item_id, guild_ref.id, img_url)
            await self._refresh(parent_interaction)
        await interaction.response.send_modal(Modal4Shop("Add Shop Item", callback=submit))

    @discord.ui.button(label="🖼️ Set Image", style=discord.ButtonStyle.blurple, row=1)
    async def btn_set_image(self, interaction: discord.Interaction, btn):
        """Upload or replace the image for an existing shop item from device (phone/computer)."""
        items = db_get_shop_items(self.guild.id)
        if not items:
            await interaction.response.send_message("❌ Shop is empty.", ephemeral=True)
            return
        options = [
            discord.SelectOption(
                label=f"{item['name'][:70]}  —  {item['price']} XP",
                description="🖼️ has image" if item.get("image_url") else "No image yet",
                value=str(item["id"])
            )
            for item in items[:25]
        ]
        view = discord.ui.View(timeout=60)
        sel = discord.ui.Select(placeholder="Choose item to add/replace image", options=options)
        guild_ref = self.guild
        parent = interaction
        all_items = items
        async def on_select(inter2):
            if inter2.user.id != self.author_id:
                await inter2.response.send_message("❌ Not your panel.", ephemeral=True)
                return
            item_id = int(sel.values[0])
            chosen = next((i for i in all_items if i["id"] == item_id), None)
            item_name = chosen["name"] if chosen else "item"
            await inter2.response.send_message(
                f"🖼️ Upload an image for **{item_name}** (jpg, png, gif…) or click Skip.",
                ephemeral=True
            )
            img_url = await _await_image_upload(bot, inter2, item_name)
            if img_url:
                db_update_shop_image(item_id, guild_ref.id, img_url)
                await inter2.followup.send(f"✅ Image updated for **{item_name}**!", ephemeral=True)
            else:
                await inter2.followup.send("⏭️ No image uploaded — skipped.", ephemeral=True)
            await self._refresh(parent)
        sel.callback = on_select
        view.add_item(sel)
        await interaction.response.send_message("🖼️ Choose an item to set its image:", view=view, ephemeral=True)

    @discord.ui.button(label="⏳ Toggle Expiry", style=discord.ButtonStyle.grey, row=1)
    async def btn_toggle_expiry(self, interaction: discord.Interaction, btn):
        """Toggle whether the expiry duration is shown in /shop for temporary items."""
        all_items = db_get_shop_items(self.guild.id)
        items = [i for i in all_items if i.get("is_temporary")]
        if not items:
            await interaction.response.send_message("❌ No temporary items in the shop.", ephemeral=True)
            return
        options = [
            discord.SelectOption(
                label=f"{item['name'][:70]}  —  {item['price']} XP",
                description="⏳ Expiry SHOWN" if item.get("show_duration", 1) else "🔇 Expiry HIDDEN",
                value=str(item["id"])
            )
            for item in items[:25]
        ]
        view = discord.ui.View(timeout=60)
        sel = discord.ui.Select(placeholder="Toggle expiry visibility", options=options)
        guild_ref = self.guild
        parent = interaction
        async def on_select(inter2):
            if inter2.user.id != self.author_id:
                await inter2.response.send_message("❌ Not your panel.", ephemeral=True)
                return
            item_id = int(sel.values[0])
            chosen = next((i for i in items if i["id"] == item_id), None)
            if not chosen:
                await inter2.response.send_message("❌ Item not found.", ephemeral=True)
                return
            new_show = 0 if chosen.get("show_duration", 1) else 1
            conn = get_db()
            conn.execute("UPDATE shop_items SET show_duration=? WHERE id=? AND guild_id=?",
                         (new_show, item_id, guild_ref.id))
            conn.commit()
            conn.close()
            label = "✅ Expiry now **shown** in /shop" if new_show else "🔇 Expiry now **hidden** in /shop"
            await inter2.response.send_message(f"{label} for **{chosen['name']}**", ephemeral=True)
            await self._refresh(parent)
        sel.callback = on_select
        view.add_item(sel)
        await interaction.response.send_message("⏳ Toggle expiry display for a temporary item:", view=view, ephemeral=True)

    @discord.ui.button(label="🗑️ Remove Item", style=discord.ButtonStyle.red, row=0)
    async def btn_remove(self, interaction: discord.Interaction, btn):
        items = db_get_shop_items(self.guild.id)
        if not items:
            await interaction.response.send_message("❌ Shop is already empty.", ephemeral=True)
            return
        options = [
            discord.SelectOption(label=f"{item['name'][:80]}  —  {item['price']} XP", value=str(item["id"]))
            for item in items[:25]
        ]
        view = discord.ui.View(timeout=60)
        sel = discord.ui.Select(placeholder="Choose an item to remove", options=options)
        async def on_select(inter2):
            if inter2.user.id != self.author_id:
                await inter2.response.send_message("❌ Not your panel.", ephemeral=True)
                return
            db_remove_shop_item(int(sel.values[0]), self.guild.id)
            await inter2.response.send_message("✅ Item removed.", ephemeral=True)
            await self._refresh(interaction)
        sel.callback = on_select
        view.add_item(sel)
        await interaction.response.send_message("🗑️ Which item would you like to remove?", view=view, ephemeral=True)

    @discord.ui.button(label="📋 View All", style=discord.ButtonStyle.grey, row=0)
    async def btn_view(self, interaction: discord.Interaction, btn):
        items = db_get_shop_items(self.guild.id)
        if not items:
            await interaction.response.send_message("The shop is empty.", ephemeral=True)
            return
        lines = []
        for i in items:
            tags = []
            if i.get("is_temporary"): tags.append(f"⏳{i['duration_days']}d")
            if i.get("requires_text"): tags.append(f"📝 {i['text_label']}")
            if i.get("image_url"): tags.append("🖼️")
            tag_str = "  " + "  ".join(tags) if tags else ""
            lines.append(f"`{i['id']}` **{i['name']}** — {i['price']} XP{tag_str}")
        e = E("🛒 All Shop Items", "\n".join(lines), C_GOLD)
        await interaction.response.send_message(embed=e, ephemeral=True)

class ConfigQuestsMenu(_SubMenu):
    def build_embed(self, config: dict) -> discord.Embed:
        e = E("📅 Quest Settings", color=C_QUEST)
        e.description = "XP rewards per rarity and enable/disable individual quests from the pool."
        e.add_field(name="🪨 Stone XP",   value=f"**{config.get('quest_xp_stone',50)} XP**",   inline=True)
        e.add_field(name="🥉 Bronze XP",  value=f"**{config.get('quest_xp_bronze',100)} XP**", inline=True)
        e.add_field(name="🥈 Silver XP",  value=f"**{config.get('quest_xp_silver',200)} XP**", inline=True)
        e.add_field(name="🥇 Gold XP",    value=f"**{config.get('quest_xp_gold',400)} XP**",   inline=True)
        e.add_field(name="💎 Diamond XP", value=f"**{config.get('quest_xp_diamond',750)} XP**",inline=True)
        e.add_field(name="🔄 Boost Quest",value=_bool(config.get("boost_quest_enabled", 1)) +
                    f" — **{config.get('boost_quest_xp',100)} XP** per boost", inline=True)
        e.set_footer(text="Quests reset monthly. Each user gets 1 random quest per rarity.")
        return e

    @discord.ui.button(label="Set Rarity XP",  style=discord.ButtonStyle.blurple, row=0)
    async def btn_rarity_xp(self, interaction: discord.Interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, v_rarity, v_xp):
            rarity = v_rarity.strip().lower()
            if rarity not in RARITIES:
                await inter.response.send_message(f"❌ Valid rarities: {', '.join(RARITIES)}", ephemeral=True)
                return
            try:
                xp = int(v_xp)
                if xp < 0: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Enter a non-negative number.", ephemeral=True)
                return
            db_set_config(self.guild.id, **{f"quest_xp_{rarity}": xp})
            await inter.response.send_message(f"✅ {rarity.capitalize()} quest XP set to **{xp} XP**", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal2(
            "Set Quest Rarity XP", "Rarity", "stone / bronze / silver / gold / diamond",
            "XP reward", "200",
            callback=submit
        ))

    @discord.ui.button(label="Toggle Boost Quest", style=discord.ButtonStyle.blurple, row=0)
    async def btn_boost_toggle(self, interaction, btn):
        config = db_get_config(self.guild.id)
        new_val = 0 if config.get("boost_quest_enabled", 1) else 1
        db_set_config(self.guild.id, boost_quest_enabled=new_val)
        await interaction.response.edit_message(embed=self.build_embed(db_get_config(self.guild.id)), view=self)

    @discord.ui.button(label="Boost Quest XP",  style=discord.ButtonStyle.blurple, row=0)
    async def btn_boost_xp(self, interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            try:
                xp = int(value)
                if xp < 0: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Enter a non-negative number.", ephemeral=True)
                return
            db_set_config(self.guild.id, boost_quest_xp=xp)
            await inter.response.send_message(f"✅ Boost quest XP set to **{xp} XP**", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1("Boost Quest XP", "XP per server boost",
            placeholder="100", default=str(config.get("boost_quest_xp", 100)), callback=submit))

    @discord.ui.button(label="Enable/Disable Quest",style=discord.ButtonStyle.grey, row=1)
    async def btn_toggle_quest(self, interaction: discord.Interaction, btn):
        # List all quest keys with enabled status
        conn = get_db()
        rows = conn.execute("SELECT quest_key, enabled FROM quest_pool_config WHERE guild_id=?",
                            (self.guild.id,)).fetchall()
        conn.close()
        status_map = {r["quest_key"]: r["enabled"] for r in rows}
        all_keys = [(r, q) for r, quests in QUEST_POOL.items() for q in quests]
        options = [
            discord.SelectOption(
                label=f"[{r.upper()}] {q['name'][:60]}",
                value=q["key"],
                description="✅ Enabled" if status_map.get(q["key"], 1) else "❌ Disabled"
            )
            for r, q in all_keys[:25]
        ]
        view = discord.ui.View(timeout=60)
        sel = discord.ui.Select(placeholder="Choose a quest to toggle", options=options)
        async def on_select(inter2):
            if inter2.user.id != self.author_id:
                await inter2.response.send_message("❌ Not your panel.", ephemeral=True)
                return
            key = sel.values[0]
            current = status_map.get(key, 1)
            new_enabled = 0 if current else 1
            conn2 = get_db()
            conn2.execute("INSERT INTO quest_pool_config (guild_id, quest_key, enabled) VALUES (?,?,?) "
                          "ON CONFLICT(guild_id, quest_key) DO UPDATE SET enabled=?",
                          (self.guild.id, key, new_enabled, new_enabled))
            conn2.commit()
            conn2.close()
            label = "✅ Enabled" if new_enabled else "❌ Disabled"
            await inter2.response.send_message(f"{label} quest: **{key}**", ephemeral=True)
        sel.callback = on_select
        view.add_item(sel)
        await interaction.response.send_message("Toggle a quest from the pool:", view=view, ephemeral=True)

class ConfigAchievementsMenu(_SubMenu):
    def build_embed(self, config: dict) -> discord.Embed:
        db_ensure_achievement_config(self.guild.id)
        e = E("🏆 Achievement Settings", color=C_ACHIEVE)
        e.description = "Configure thresholds and Discord roles for each achievement tier."
        for ach_def in ACHIEVEMENT_DEFS:
            tiers = db_get_achievement_config(self.guild.id, ach_def["key"])
            tier_lines = []
            for t in tiers[:5]:
                role_str = f"<@&{t['role_id']}>" if t.get("role_id") else "`No role`"
                enabled_str = "" if t.get("enabled", 1) else " ❌"
                tier_lines.append(f"Tier {t['tier'] + 1}: **{t['threshold']}** → {role_str}{enabled_str}")
            e.add_field(
                name=f"{ach_def['name']} ({ach_def['category']})",
                value="\n".join(tier_lines) if tier_lines else "`Default thresholds, no roles set`",
                inline=False
            )
        e.add_field(name="📢 Announcement Channel", value=_ch(config.get("achievement_channel_id")), inline=False)
        return e

    @discord.ui.button(label="Set Tier Role",    style=discord.ButtonStyle.blurple, row=0)
    async def btn_role(self, interaction: discord.Interaction, btn):
        async def submit(inter, v_ach, v_tier, v_role):
            # Find achievement
            ach = next((a for a in ACHIEVEMENT_DEFS if a["key"].lower() == v_ach.strip().lower()), None)
            if not ach:
                keys = ", ".join(a["key"] for a in ACHIEVEMENT_DEFS)
                await inter.response.send_message(f"❌ Unknown achievement. Valid: {keys}", ephemeral=True)
                return
            try:
                tier_display = int(v_tier.strip())
                if tier_display < 1 or tier_display > 5: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Tier must be 1–5.", ephemeral=True)
                return
            tier = tier_display - 1  # convert to 0-indexed for storage
            role_id = parse_role_id(v_role.strip()) if v_role.strip() else None
            db_ensure_achievement_config(self.guild.id)
            conn = get_db()
            default_threshold = ach["tiers"][tier] if tier < len(ach["tiers"]) else 0
            conn.execute(
                "INSERT INTO achievement_config (guild_id, achievement_key, tier, threshold, role_id) VALUES (?,?,?,?,?) "
                "ON CONFLICT(guild_id, achievement_key, tier) DO UPDATE SET role_id=?",
                (self.guild.id, ach["key"], tier, default_threshold, role_id, role_id)
            )
            conn.commit()
            conn.close()
            role_str = f"<@&{role_id}>" if role_id else "removed"
            await inter.response.send_message(
                f"✅ **{ach['name']}** Tier {tier_display} role set to {role_str}", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal3(
            "Set Achievement Role",
            "Achievement key", "shares / invites / streak / boosts / quests",
            "Tier (1–5)", "1 = I,  2 = II,  3 = III,  4 = IV,  5 = V",
            "Role mention or ID (empty = remove)", "@RoleName  or  1234567890",
            callback=submit
        ))

    @discord.ui.button(label="Set Threshold",   style=discord.ButtonStyle.blurple, row=0)
    async def btn_threshold(self, interaction: discord.Interaction, btn):
        async def submit(inter, v_ach, v_tier, v_threshold):
            ach = next((a for a in ACHIEVEMENT_DEFS if a["key"].lower() == v_ach.strip().lower()), None)
            if not ach:
                await inter.response.send_message("❌ Unknown achievement key.", ephemeral=True)
                return
            try:
                tier_display = int(v_tier.strip())
                threshold = int(v_threshold.strip())
                if tier_display < 1 or tier_display > 5 or threshold < 1: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Invalid tier (1–5) or threshold.", ephemeral=True)
                return
            tier = tier_display - 1  # convert to 0-indexed for storage
            db_ensure_achievement_config(self.guild.id)
            conn = get_db()
            conn.execute(
                "INSERT INTO achievement_config (guild_id, achievement_key, tier, threshold) VALUES (?,?,?,?) "
                "ON CONFLICT(guild_id, achievement_key, tier) DO UPDATE SET threshold=?",
                (self.guild.id, ach["key"], tier, threshold, threshold)
            )
            conn.commit()
            conn.close()
            await inter.response.send_message(
                f"✅ **{ach['name']}** Tier {tier_display} threshold set to **{threshold}**", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal3(
            "Set Achievement Threshold",
            "Achievement key", "shares / invites / streak / boosts / quests",
            "Tier (1–5)", "1",
            "Required amount", "50",
            callback=submit
        ))

    @discord.ui.button(label="Achievement Channel", style=discord.ButtonStyle.grey, row=1)
    async def btn_ch(self, interaction: discord.Interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            if not value.strip():
                db_set_config(self.guild.id, achievement_channel_id=None)
                await inter.response.send_message("✅ Achievement channel removed.", ephemeral=True)
                await self._refresh(interaction)
                return
            ch_id = parse_channel_id(value)
            if not ch_id:
                await inter.response.send_message("❌ Invalid channel.", ephemeral=True)
                return
            db_set_config(self.guild.id, achievement_channel_id=ch_id)
            await inter.response.send_message(f"✅ Achievement channel set to <#{ch_id}>", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1("Achievement Channel", "Channel mention or ID (empty = disable)",
            placeholder="#achievements  or  1234567890",
            default=str(config.get("achievement_channel_id") or ""), required=False, callback=submit))

class ConfigEventsMenu(_SubMenu):
    def build_embed(self, config: dict) -> discord.Embed:
        events = db_get_all_events(self.guild.id)
        e = E("🎉 Events", color=C_EVENT)
        if not events:
            e.description = "No events created yet. Add a Double XP event or Community Goal."
        else:
            now = datetime.now().isoformat()
            for ev in events[:6]:
                status = "🟢 Active" if (ev["enabled"] and ev["start_date"] <= now <= ev["end_date"]) else \
                         "⏳ Upcoming" if (ev["enabled"] and now < ev["start_date"]) else \
                         "🔴 Ended/Disabled"
                e.add_field(
                    name=f"{status} — {ev['name']} [{ev['event_type']}]",
                    value=f"{ev['start_date'][:10]} → {ev['end_date'][:10]}  ID:`{ev['id']}`",
                    inline=False
                )
        return e

    @discord.ui.button(label="➕ Add Double XP Event", style=discord.ButtonStyle.green, row=0)
    async def btn_add_dxp(self, interaction: discord.Interaction, btn):
        async def submit(inter, v_name, v_start, v_end):
            try:
                start_dt = datetime.strptime(v_start.strip(), "%Y-%m-%d")
                end_dt   = datetime.strptime(v_end.strip(), "%Y-%m-%d")
                if end_dt < start_dt: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Use YYYY-MM-DD format. End must be after start.", ephemeral=True)
                return
            config = db_get_config(self.guild.id)
            mult = config.get("event_double_xp_mult", 2.0)
            conn = get_db()
            conn.execute(
                "INSERT INTO events (guild_id, name, description, event_type, start_date, end_date, config_json) VALUES (?,?,?,?,?,?,?)",
                (self.guild.id, v_name.strip(), f"Double XP event (×{mult})", "double_xp",
                 start_dt.isoformat(), end_dt.replace(hour=23, minute=59, second=59).isoformat(),
                 json.dumps({"multiplier": mult}))
            )
            conn.commit()
            conn.close()
            await inter.response.send_message(f"✅ Double XP event **{v_name.strip()}** created.", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal3(
            "Add Double XP Event",
            "Event name", "Double XP Weekend",
            "Start date", "YYYY-MM-DD",
            "End date", "YYYY-MM-DD",
            callback=submit
        ))

    @discord.ui.button(label="➕ Add Community Goal", style=discord.ButtonStyle.green, row=0)
    async def btn_add_goal(self, interaction: discord.Interaction, btn):
        async def submit(inter, v_name, v_target, v_xp):
            try:
                target = int(v_target.strip())
                xp = int(v_xp.strip())
                if target <= 0 or xp < 0: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Target must be positive, XP non-negative.", ephemeral=True)
                return
            conn = get_db()
            ev_row = conn.execute(
                "INSERT INTO events (guild_id, name, description, event_type, start_date, end_date, config_json) VALUES (?,?,?,?,?,?,?)",
                (self.guild.id, v_name.strip(), f"Community goal: {target} shares", "community_goal",
                 datetime.now().isoformat(),
                 (datetime.now() + timedelta(days=30)).isoformat(),
                 json.dumps({"goal_type": "share_videos", "target": target, "reward_xp": xp}))
            )
            ev_id = ev_row.lastrowid
            conn.execute(
                "INSERT INTO community_goals (guild_id, event_id, name, goal_type, target, reward_xp) VALUES (?,?,?,?,?,?)",
                (self.guild.id, ev_id, v_name.strip(), "share_videos", target, xp)
            )
            conn.commit()
            conn.close()
            await inter.response.send_message(
                f"✅ Community goal **{v_name.strip()}** created.\nTarget: {target} shares → {xp} XP per contributor.",
                ephemeral=True
            )
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal3(
            "Add Community Goal",
            "Goal name", "100 Supporter Challenge",
            "Target (e.g. number of shares)", "100",
            "XP reward per contributor", "150",
            callback=submit
        ))

    @discord.ui.button(label="Toggle Event",  style=discord.ButtonStyle.grey, row=1)
    async def btn_toggle(self, interaction: discord.Interaction, btn):
        events = db_get_all_events(self.guild.id)
        if not events:
            await interaction.response.send_message("❌ No events created.", ephemeral=True)
            return
        options = [
            discord.SelectOption(
                label=f"{ev['name'][:60]}  [{ev['event_type']}]",
                value=str(ev["id"]),
                description="✅ Enabled" if ev["enabled"] else "❌ Disabled"
            )
            for ev in events[:25]
        ]
        view = discord.ui.View(timeout=60)
        sel = discord.ui.Select(placeholder="Choose event to toggle", options=options)
        async def on_select(inter2):
            if inter2.user.id != self.author_id:
                await inter2.response.send_message("❌ Not your panel.", ephemeral=True)
                return
            ev_id = int(sel.values[0])
            conn = get_db()
            row = conn.execute("SELECT enabled FROM events WHERE id=?", (ev_id,)).fetchone()
            if row:
                conn.execute("UPDATE events SET enabled=? WHERE id=?", (0 if row["enabled"] else 1, ev_id))
                conn.commit()
            conn.close()
            await inter2.response.send_message("✅ Event toggled.", ephemeral=True)
            await self._refresh(interaction)
        sel.callback = on_select
        view.add_item(sel)
        await interaction.response.send_message("Toggle an event:", view=view, ephemeral=True)

    @discord.ui.button(label="Set Double XP Multiplier", style=discord.ButtonStyle.grey, row=1)
    async def btn_mult(self, interaction: discord.Interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            try:
                mult = float(value.strip())
                if mult < 1: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Must be a number ≥ 1 (e.g. 2.0).", ephemeral=True)
                return
            db_set_config(self.guild.id, event_double_xp_mult=mult)
            await inter.response.send_message(f"✅ Default Double XP multiplier set to **×{mult}**", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1("Double XP Multiplier",
            "Multiplier (e.g. 2 = double, 3 = triple)",
            placeholder="2.0", default=str(config.get("event_double_xp_mult", 2.0)), callback=submit))

class ConfigPermissionsMenu(_SubMenu):
    def build_embed(self, config: dict) -> discord.Embed:
        role_id = config.get("manager_role_id")
        e = E("👥 Permissions", color=C_MAIN)
        e.description = (
            "**XP Manager** is the single role controlling this bot.\n"
            "Members with this role can award XP, use `/admin`, and use `/config`.\n\u200b"
        )
        e.add_field(name="👥 XP Manager Role", value=_role(role_id), inline=False)
        if not role_id:
            e.add_field(name="⚠️ No role set",
                        value="Any Discord administrator can access the bot until a role is assigned.",
                        inline=False)
        return e

    @discord.ui.button(label="Set XP Manager Role",    style=discord.ButtonStyle.blurple, row=0)
    async def btn_set(self, interaction: discord.Interaction, btn):
        config = db_get_config(self.guild.id)
        async def submit(inter, value):
            if not value.strip():
                db_set_config(self.guild.id, manager_role_id=None)
                await inter.response.send_message("✅ XP Manager role removed.", ephemeral=True)
                await self._refresh(interaction)
                return
            role_id = parse_role_id(value)
            if not role_id:
                await inter.response.send_message("❌ Invalid role. Mention it or paste its ID.", ephemeral=True)
                return
            db_set_config(self.guild.id, manager_role_id=role_id)
            await inter.response.send_message(f"✅ XP Manager role set to <@&{role_id}>", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal1("Set XP Manager Role",
            "Role mention or ID (empty = remove)",
            placeholder="@XP-Manager  or  1234567890",
            default=str(config.get("manager_role_id") or ""), required=False, callback=submit))

# ══════════════════════════════════════════════════════════════
#  /admin — PANEL
# ══════════════════════════════════════════════════════════════

def admin_main_embed(guild: discord.Guild) -> discord.Embed:
    e = E(f"🛠️ Admin Panel — {guild.name}", color=C_INFO)
    e.description = "Manage XP, shop, announcements, backups, and community goals."
    return e

class AdminMainMenu(discord.ui.View):
    def __init__(self, guild: discord.Guild, author_id: int):
        super().__init__(timeout=300)
        self.guild = guild
        self.author_id = author_id

    async def interaction_check(self, i): 
        if i.user.id != self.author_id:
            await i.response.send_message("❌ Not your panel.", ephemeral=True)
            return False
        return True

    async def _go(self, i, embed, view):
        await i.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="👤 Manage XP",        style=discord.ButtonStyle.blurple, row=0)
    async def cat_xp(self, i, b):
        sub = AdminXPMenu(self.guild, self.author_id)
        await self._go(i, sub.build_embed(), sub)

    @discord.ui.button(label="🛒 Manage Shop",      style=discord.ButtonStyle.blurple, row=0)
    async def cat_shop(self, i, b):
        sub = AdminShopMenu(self.guild, self.author_id)
        await self._go(i, sub.build_embed(), sub)

    @discord.ui.button(label="📢 Trigger Ping",     style=discord.ButtonStyle.blurple, row=0)
    async def cat_announce(self, i: discord.Interaction, b):
        config = db_get_config(self.guild.id)
        if not config.get("share_channel_id"):
            await i.response.send_message("❌ No share channel configured.", ephemeral=True)
            return
        async def submit(inter, value):
            vid_id = extract_video_id(value)
            if not vid_id:
                await inter.response.send_message("❌ Invalid YouTube URL.", ephemeral=True)
                return
            db_set_current_video(self.guild.id, vid_id, make_shorts_url(vid_id), "Manually triggered")
            await inter.response.send_message("📢 Sending ping...", ephemeral=True)
            await announce_video(inter.client, self.guild.id, vid_id, make_shorts_url(vid_id), "Manually triggered")
            await inter.edit_original_response(content="✅ Ping sent to share channel!")
        await i.response.send_modal(Modal1("Trigger Share Ping", "YouTube video URL",
            placeholder="https://youtube.com/shorts/xxxx", callback=submit))

    @discord.ui.button(label="💾 Run Backup",       style=discord.ButtonStyle.grey, row=1)
    async def cat_backup(self, i: discord.Interaction, b):
        config = db_get_config(self.guild.id)
        if not config.get("backup_channel_id"):
            await i.response.send_message("❌ No backup channel configured.", ephemeral=True)
            return
        await i.response.send_message("💾 Running backup...", ephemeral=True)
        await do_backup(i.client, self.guild.id)
        await i.followup.send("✅ Backup sent!", ephemeral=True)

    @discord.ui.button(label="📊 Server Stats",     style=discord.ButtonStyle.grey, row=1)
    async def cat_stats(self, i: discord.Interaction, b):
        conn = get_db()
        member_count = conn.execute("SELECT COUNT(*) FROM xp_data WHERE guild_id=?", (self.guild.id,)).fetchone()[0]
        total_xp     = conn.execute("SELECT COALESCE(SUM(xp),0) FROM xp_data WHERE guild_id=?", (self.guild.id,)).fetchone()[0]
        shop_count   = conn.execute("SELECT COUNT(*) FROM shop_items WHERE guild_id=?", (self.guild.id,)).fetchone()[0]
        share_count  = conn.execute("SELECT COUNT(*) FROM video_shares WHERE guild_id=?", (self.guild.id,)).fetchone()[0]
        quest_done   = conn.execute("SELECT COUNT(*) FROM monthly_quests WHERE guild_id=? AND completed=1", (self.guild.id,)).fetchone()[0]
        conn.close()
        current = db_get_current_video(self.guild.id)
        e = E(f"📊 Stats — {self.guild.name}", color=C_INFO)
        e.add_field(name="👥 Members with XP", value=f"**{member_count}**",   inline=True)
        e.add_field(name="💰 Total XP given",   value=f"**{total_xp} XP**",   inline=True)
        e.add_field(name="🛒 Shop items",        value=f"**{shop_count}**",    inline=True)
        e.add_field(name="🔗 Total shares",      value=f"**{share_count}**",   inline=True)
        e.add_field(name="📅 Quests completed",  value=f"**{quest_done}**",    inline=True)
        if current:
            e.add_field(name="🎬 Current video",
                        value=f"[{current['video_title']}]({make_shorts_url(current['video_id'])})", inline=False)
        await i.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="🏁 Community Goals", style=discord.ButtonStyle.grey, row=1)
    async def cat_goals(self, i: discord.Interaction, b):
        goals = db_get_community_goals(self.guild.id)
        if not goals:
            await i.response.send_message("❌ No community goals active.", ephemeral=True)
            return
        e = E("🏁 Community Goals", color=C_EVENT)
        for g in goals[:10]:
            bar = "█" * int((g["current"] / g["target"]) * 10) + "░" * (10 - int((g["current"] / g["target"]) * 10))
            e.add_field(
                name=f"{'✅ ' if g['completed'] else ''}{g['name']}",
                value=f"`{bar}` {g['current']}/{g['target']}\n{len(json.loads(g['contributors']))} contributors → {g['reward_xp']} XP each",
                inline=False
            )
        await i.response.send_message(embed=e, ephemeral=True)

class AdminXPMenu(discord.ui.View):
    def __init__(self, guild, author_id):
        super().__init__(timeout=300)
        self.guild = guild
        self.author_id = author_id

    async def interaction_check(self, i):
        if i.user.id != self.author_id:
            await i.response.send_message("❌ Not your panel.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        e = E("👤 Manage XP", color=C_INFO)
        e.description = "Add, remove, set, or reset a member's XP balance."
        return e

    async def _back(self, i):
        main = AdminMainMenu(self.guild, self.author_id)
        await i.response.edit_message(embed=admin_main_embed(self.guild), view=main)

    @discord.ui.button(label="← Back",           style=discord.ButtonStyle.grey,   row=4)
    async def btn_back(self, i, b): await self._back(i)

    @discord.ui.button(label="➕ Add / Remove",   style=discord.ButtonStyle.green,  row=0)
    async def btn_add(self, interaction: discord.Interaction, btn):
        async def submit(inter, v_member, v_amount):
            uid = parse_user_id(v_member)
            if not uid:
                await inter.response.send_message("❌ Invalid member.", ephemeral=True)
                return
            try:
                amount = int(v_amount)
            except ValueError:
                await inter.response.send_message("❌ Invalid amount.", ephemeral=True)
                return
            new_xp = db_add_xp(self.guild.id, uid, amount)
            verb = "received" if amount >= 0 else "lost"
            await inter.response.send_message(
                f"✅ <@{uid}> {verb} **{abs(amount)} XP** — balance: **{new_xp} XP**", ephemeral=True)
            await send_log(inter.client, self.guild.id, inter.user, "XP Modified",
                           f"Member: <@{uid}> | Change: {amount:+d} XP | Balance: {new_xp} XP")
        await interaction.response.send_modal(Modal2("Add / Remove XP",
            "Member mention or ID", "@username  or  1234567890",
            "Amount (negative = remove)", "100  or  -50", callback=submit))

    @discord.ui.button(label="📊 Set Exact",      style=discord.ButtonStyle.blurple, row=0)
    async def btn_set(self, interaction: discord.Interaction, btn):
        async def submit(inter, v_member, v_amount):
            uid = parse_user_id(v_member)
            if not uid:
                await inter.response.send_message("❌ Invalid member.", ephemeral=True)
                return
            try:
                amount = int(v_amount)
                if amount < 0: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Amount must be non-negative.", ephemeral=True)
                return
            db_set_xp(self.guild.id, uid, amount)
            await inter.response.send_message(f"✅ Set <@{uid}>'s XP to **{amount} XP**", ephemeral=True)
            await send_log(inter.client, self.guild.id, inter.user, "XP Set",
                           f"Member: <@{uid}> | Balance: {amount} XP")
        await interaction.response.send_modal(Modal2("Set Exact XP",
            "Member mention or ID", "@username  or  1234567890",
            "New XP amount", "500", callback=submit))

    @discord.ui.button(label="🔄 Reset XP",       style=discord.ButtonStyle.red,    row=0)
    async def btn_reset(self, interaction: discord.Interaction, btn):
        async def submit(inter, value):
            uid = parse_user_id(value)
            if not uid:
                await inter.response.send_message("❌ Invalid member.", ephemeral=True)
                return
            old = db_get_xp(self.guild.id, uid)
            view = ConfirmView(inter.user.id)
            await inter.response.send_message(f"⚠️ Reset <@{uid}>'s XP to 0? (was {old} XP)", view=view, ephemeral=True)
            await view.wait()
            if view.value:
                db_set_xp(self.guild.id, uid, 0)
                await inter.followup.send(f"✅ <@{uid}>'s XP reset to 0.", ephemeral=True)
                await send_log(inter.client, self.guild.id, inter.user, "XP Reset",
                               f"Member: <@{uid}> | Previous XP: {old}")
            else:
                await inter.followup.send("Cancelled.", ephemeral=True)
        await interaction.response.send_modal(Modal1("Reset Member XP", "Member mention or ID",
            placeholder="@username  or  1234567890", callback=submit))

    @discord.ui.button(label="🔄 Reset Streak",   style=discord.ButtonStyle.red,    row=1)
    async def btn_reset_streak(self, interaction: discord.Interaction, btn):
        async def submit(inter, value):
            uid = parse_user_id(value)
            if not uid:
                await inter.response.send_message("❌ Invalid member.", ephemeral=True)
                return
            db_update_streak(self.guild.id, uid, 0, "")
            guild = inter.client.get_guild(self.guild.id)
            if guild:
                await update_streak_nickname(guild, uid, 0)
            await inter.response.send_message(f"✅ <@{uid}>'s streak reset to 0.", ephemeral=True)
        await interaction.response.send_modal(Modal1("Reset Member Streak", "Member mention or ID",
            placeholder="@username  or  1234567890", callback=submit))

    @discord.ui.button(label="🔍 Check XP",       style=discord.ButtonStyle.grey,   row=1)
    async def btn_check(self, interaction: discord.Interaction, btn):
        async def submit(inter, value):
            uid = parse_user_id(value)
            if not uid:
                await inter.response.send_message("❌ Invalid member.", ephemeral=True)
                return
            xp = db_get_xp(self.guild.id, uid)
            top = db_top_xp(self.guild.id, limit=1000)
            rank = next((i+1 for i, (u, _) in enumerate(top) if u == uid), None)
            streak = db_get_streak(self.guild.id, uid)
            await inter.response.send_message(
                f"<@{uid}> — **{xp} XP**" +
                (f"  |  Rank **#{rank}**" if rank else "") +
                f"  |  Streak **🔥{streak['current_streak']}**",
                ephemeral=True
            )
        await interaction.response.send_modal(Modal1("Check Member XP", "Member mention or ID",
            placeholder="@username  or  1234567890", callback=submit))

class AdminShopMenu(discord.ui.View):
    def __init__(self, guild, author_id):
        super().__init__(timeout=300)
        self.guild = guild
        self.author_id = author_id

    async def interaction_check(self, i):
        if i.user.id != self.author_id:
            await i.response.send_message("❌ Not your panel.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        items = db_get_shop_items(self.guild.id)
        e = E("🛒 Manage Shop", color=C_GOLD)
        if not items:
            e.description = "Shop is empty."
        else:
            for item in items[:15]:
                tags = []
                if item.get("is_temporary"): tags.append(f"⏳{item['duration_days']}d")
                if item.get("requires_text"): tags.append(f"📝")
                e.add_field(name=f"{item['name']}", value=f"**{item['price']} XP** ID:`{item['id']}`{'  '+''.join(tags) if tags else ''}", inline=True)
        return e

    async def _back(self, i):
        main = AdminMainMenu(self.guild, self.author_id)
        await i.response.edit_message(embed=admin_main_embed(self.guild), view=main)

    async def _refresh(self, interaction):
        await interaction.edit_original_response(embed=self.build_embed(), view=self)

    @discord.ui.button(label="← Back",       style=discord.ButtonStyle.grey,  row=4)
    async def btn_back(self, i, b): await self._back(i)

    @discord.ui.button(label="➕ Add Item",   style=discord.ButtonStyle.green, row=0)
    async def btn_add(self, interaction: discord.Interaction, btn):
        async def submit(inter, v_name, v_price, v_image, v_temp, v_text):
            try:
                price = int(v_price); days = int(v_temp)
                if price <= 0 or days < 0: raise ValueError
            except ValueError:
                await inter.response.send_message("❌ Invalid price or duration.", ephemeral=True)
                return
            item_id = db_add_shop_item(
                self.guild.id, v_name.strip(), price, v_image.strip() or None,
                1 if days > 0 else 0, days if days > 0 else None, 1,
                1 if v_text.strip() else 0, v_text.strip() or None
            )
            await inter.response.send_message(f"✅ Added **{v_name.strip()}** (ID: `{item_id}`)", ephemeral=True)
            await self._refresh(interaction)
        await interaction.response.send_modal(Modal5("Add Shop Item", callback=submit))

    @discord.ui.button(label="🗑️ Remove",    style=discord.ButtonStyle.red,   row=0)
    async def btn_remove(self, interaction: discord.Interaction, btn):
        items = db_get_shop_items(self.guild.id)
        if not items:
            await interaction.response.send_message("❌ Shop is empty.", ephemeral=True)
            return
        options = [discord.SelectOption(label=f"{i['name'][:80]} — {i['price']} XP", value=str(i["id"])) for i in items[:25]]
        view = discord.ui.View(timeout=60)
        sel = discord.ui.Select(placeholder="Choose item to remove", options=options)
        async def on_select(inter2):
            db_remove_shop_item(int(sel.values[0]), self.guild.id)
            await inter2.response.send_message("✅ Removed.", ephemeral=True)
            await self._refresh(interaction)
        sel.callback = on_select
        view.add_item(sel)
        await interaction.response.send_message("Select item to remove:", view=view, ephemeral=True)

# ══════════════════════════════════════════════════════════════
#  /shop — MEMBER SHOP VIEW
# ══════════════════════════════════════════════════════════════

class ShopView(discord.ui.View):
    PER_PAGE = 5

    def __init__(self, guild: discord.Guild, user: discord.Member, page: int = 0):
        super().__init__(timeout=120)
        self.guild = guild
        self.user = user
        self.page = page
        self.items = db_get_shop_items(guild.id)
        self._build()

    def _build(self):
        self.clear_items()
        start = self.page * self.PER_PAGE
        page_items = self.items[start:start + self.PER_PAGE]
        user_xp = db_get_xp(self.guild.id, self.user.id)
        for item in page_items:
            affordable = user_xp >= item["price"]
            label_parts = [item["name"][:50], f"— {item['price']} XP"]
            if item.get("is_temporary") and item.get("show_duration"): label_parts.append(f"⏳{item['duration_days']}d")
            btn = discord.ui.Button(
                label="  ".join(label_parts)[:80],
                style=discord.ButtonStyle.blurple if affordable else discord.ButtonStyle.grey,
                disabled=not affordable, row=0
            )
            btn.callback = self._buy_cb(item)
            self.add_item(btn)
        total = max(1, -(-len(self.items) // self.PER_PAGE))
        if self.page > 0:
            prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.grey, row=4)
            prev.callback = self._prev
            self.add_item(prev)
        if self.page < total - 1:
            nxt = discord.ui.Button(label="▶", style=discord.ButtonStyle.grey, row=4)
            nxt.callback = self._next
            self.add_item(nxt)

    def embed(self) -> discord.Embed:
        user_xp = db_get_xp(self.guild.id, self.user.id)
        start = self.page * self.PER_PAGE
        page_items = self.items[start:start + self.PER_PAGE]
        total = max(1, -(-len(self.items) // self.PER_PAGE))
        e = E(f"🛒 Shop — {self.guild.name}", color=C_GOLD)
        e.description = f"💰 Your balance: **{user_xp} XP**\nClick an item to purchase it."
        if not self.items:
            e.description = "⚠️ The shop is empty. Ask an XP Manager to add items via `/admin`."
        else:
            for item in page_items:
                status = "✅" if user_xp >= item["price"] else "❌"
                extras = []
                if item.get("is_temporary") and item.get("show_duration"): extras.append(f"⏳ {item['duration_days']} days")
                if item.get("requires_text"): extras.append(f"📝 {item['text_label'] or 'Text required'}")
                if item.get("image_url"): extras.append("🖼️")
                e.add_field(
                    name=f"{status} {item['name']}",
                    value=f"**{item['price']} XP**" + ("  " + "  ".join(extras) if extras else ""),
                    inline=True
                )
                if item.get("image_url"):
                    e.set_thumbnail(url=item["image_url"])
        e.set_footer(text=f"Page {self.page+1}/{total}")
        return e

    def _buy_cb(self, item):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user.id:
                await interaction.response.send_message("❌ This isn't your shop!", ephemeral=True)
                return
            user_xp = db_get_xp(self.guild.id, self.user.id)
            if user_xp < item["price"]:
                await interaction.response.send_message(
                    f"❌ Not enough XP. Need **{item['price']}**, have **{user_xp}**.", ephemeral=True)
                return
            # If item requires text, ask for it first
            if item.get("requires_text"):
                async def text_submit(inter, value):
                    await _complete_purchase(inter, item, value.strip())
                await interaction.response.send_modal(Modal1(
                    f"Complete Purchase — {item['name'][:40]}",
                    label=item.get("text_label") or "Required information",
                    placeholder="Enter the required information",
                    callback=text_submit
                ))
            else:
                view = ConfirmView(interaction.user.id)
                await interaction.response.send_message(
                    f"🛒 Buy **{item['name']}** for **{item['price']} XP**?\n"
                    f"Remaining: **{user_xp - item['price']} XP**",
                    view=view, ephemeral=True
                )
                await view.wait()
                if view.value:
                    await _complete_purchase(interaction, item, None)
                else:
                    await interaction.followup.send("Purchase cancelled.", ephemeral=True)

        async def _complete_purchase(inter: discord.Interaction, shop_item, item_text: Optional[str]):
            check_xp = db_get_xp(self.guild.id, self.user.id)
            if check_xp < shop_item["price"]:
                msg = "❌ Insufficient XP."
                if inter.response.is_done():
                    await inter.followup.send(msg, ephemeral=True)
                else:
                    await inter.response.send_message(msg, ephemeral=True)
                return
            new_xp = db_add_xp(self.guild.id, self.user.id, -shop_item["price"])
            expires_at = None
            if shop_item.get("is_temporary") and shop_item.get("duration_days"):
                expires_at = (datetime.now() + timedelta(days=shop_item["duration_days"])).isoformat()
            db_add_inventory(self.guild.id, self.user.id, shop_item["name"], expires_at, item_text)
            success_msg = (
                f"✅ **{shop_item['name']}** added to your inventory!\n"
                f"Remaining XP: **{new_xp} XP**"
            )
            if shop_item.get("is_temporary") and shop_item.get("show_duration"):
                success_msg += f"\n⏳ Expires in **{shop_item['duration_days']} days**"
            if inter.response.is_done():
                await inter.followup.send(success_msg, ephemeral=True)
            else:
                await inter.response.send_message(success_msg, ephemeral=True)
            # Notify admin if text was submitted
            if item_text:
                e = E("📝 Shop Order — Text Required",
                      f"**Item:** {shop_item['name']}\n**Buyer:** <@{self.user.id}>\n**Info:** {item_text}",
                      C_INFO)
                await notify_admin(inter.client, self.guild.id, embed=e)
            # Refresh shop
            self.items = db_get_shop_items(self.guild.id)
            self._build()
            try:
                if inter.response.is_done():
                    await inter.edit_original_response(embed=self.embed(), view=self)
            except Exception:
                pass

        return callback

    async def _prev(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Not your shop!", ephemeral=True)
            return
        self.page -= 1; self._build()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Not your shop!", ephemeral=True)
            return
        self.page += 1; self._build()
        await interaction.response.edit_message(embed=self.embed(), view=self)

# ══════════════════════════════════════════════════════════════
#  BOT SETUP
# ══════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
intents.members          = True
intents.reactions        = True
intents.guilds           = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ══════════════════════════════════════════════════════════════
#  BACKGROUND TASKS
# ══════════════════════════════════════════════════════════════

@tasks.loop(minutes=1)
async def check_youtube():
    await bot.wait_until_ready()
    conn = get_db()
    guilds = conn.execute(
        "SELECT guild_id, youtube_channel_id FROM guild_config WHERE youtube_channel_id IS NOT NULL"
    ).fetchall()
    conn.close()
    for row in guilds:
        guild_id = row["guild_id"]
        yt_id    = row["youtube_channel_id"]
        videos   = await fetch_latest_videos(yt_id)
        if not videos:
            continue
        latest  = videos[0]
        current = db_get_current_video(guild_id)
        if current and current["video_id"] == latest["video_id"]:
            continue
        print(f"[YouTube] New video for guild {guild_id}: {latest['video_id']}")
        db_set_current_video(guild_id, latest["video_id"], latest["url"], latest["title"])
        await announce_video(bot, guild_id, latest["video_id"], latest["url"], latest["title"])

@tasks.loop(minutes=15)
async def auto_backup():
    await bot.wait_until_ready()
    conn = get_db()
    guilds = conn.execute("SELECT guild_id FROM guild_config WHERE backup_channel_id IS NOT NULL").fetchall()
    conn.close()
    for row in guilds:
        await do_backup(bot, row["guild_id"])

@tasks.loop(hours=1)
async def check_expired_items():
    """Mark expired inventory items and notify admin channel."""
    await bot.wait_until_ready()
    now = datetime.now().isoformat()
    conn = get_db()
    expired = conn.execute(
        "SELECT * FROM inventory WHERE is_expired=0 AND expires_at IS NOT NULL AND expires_at <= ?",
        (now,)
    ).fetchall()
    for row in expired:
        conn.execute("UPDATE inventory SET is_expired=1 WHERE id=?", (row["id"],))
        conn.commit()
        guild_id = row["guild_id"]
        user_id  = row["user_id"]
        e = E("⏳ Item Expired",
              f"**Item:** {row['item_name']}\n**Member:** <@{user_id}>",
              C_ERROR)
        await notify_admin(bot, guild_id, embed=e)
    conn.close()

@tasks.loop(hours=24)
async def check_community_goals():
    """Check if any community goals completed and distribute rewards."""
    await bot.wait_until_ready()
    conn = get_db()
    goals = conn.execute(
        "SELECT * FROM community_goals WHERE completed=1 AND enabled=1"
    ).fetchall()
    # Mark as distributed (disable)
    for g in goals:
        contribs = json.loads(g["contributors"] or "[]")
        for uid in contribs:
            db_add_xp(g["guild_id"], uid, g["reward_xp"])
        if contribs:
            e = E("🏁 Community Goal Completed!",
                  f"**{g['name']}**\n{len(contribs)} contributors each earned **+{g['reward_xp']} XP**!",
                  C_EVENT)
            await notify_xp(bot, g["guild_id"], embed=e)
        conn.execute("UPDATE community_goals SET enabled=0 WHERE id=?", (g["id"],))
        conn.commit()
    conn.close()

@tasks.loop(minutes=1)
async def check_streak_reminders():
    """DM members with an active streak who haven't shared the current video and have < 5 min left."""
    await bot.wait_until_ready()
    now_ts = int(datetime.utcnow().timestamp())
    conn = get_db()
    videos = conn.execute(
        "SELECT cv.guild_id, cv.video_id, cv.deadline_ts "
        "FROM current_video cv "
        "JOIN guild_config gc ON gc.guild_id = cv.guild_id "
        "WHERE cv.deadline_ts IS NOT NULL "
        "AND cv.deadline_ts > ? "
        "AND cv.deadline_ts - ? <= 300 "  # 5 minutes = 300 seconds
        "AND gc.streak_reminder_enabled = 1",
        (now_ts, now_ts)
    ).fetchall()
    for row in videos:
        guild_id  = row["guild_id"]
        video_id  = row["video_id"]
        deadline  = row["deadline_ts"]
        guild = bot.get_guild(guild_id)
        if not guild:
            continue
        # Find members with a streak who haven't shared this video
        streaks = conn.execute(
            "SELECT user_id, current_streak FROM streaks WHERE guild_id=? AND current_streak > 0",
            (guild_id,)
        ).fetchall()
        for s in streaks:
            uid = s["user_id"]
            if db_has_shared(guild_id, video_id, uid):
                continue
            member = guild.get_member(uid)
            if not member or member.bot:
                continue
            try:
                await member.send(
                    f"⚠️ **Streak Alert!** Your 🔥 **{s['current_streak']}-video streak** is at risk!\n"
                    f"You have less than 5 minutes to share the video — <t:{deadline}:R>\n"
                    f"Go share it now to keep your streak alive!"
                )
            except discord.Forbidden:
                pass
    conn.close()


# ══════════════════════════════════════════════════════════════
#  EVENTS
# ══════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")
    await restore_from_discord(bot)
    init_db()
    # Cache invites for all guilds
    for guild in bot.guilds:
        db_ensure_config(guild.id)
        db_ensure_achievement_config(guild.id)
        try:
            invites = await guild.invites()
            db_cache_invites(guild.id, invites)
        except Exception:
            pass
    for loop in [check_youtube, auto_backup, check_expired_items, check_community_goals, check_streak_reminders]:
        if not loop.is_running():
            loop.start()
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"❌ Slash sync error: {e}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    db_ensure_config(guild.id)
    db_ensure_achievement_config(guild.id)
    try:
        invites = await guild.invites()
        db_cache_invites(guild.id, invites)
    except Exception:
        pass
    print(f"[+] Joined: {guild.name} ({guild.id})")

@bot.event
async def on_invite_create(invite: discord.Invite):
    if invite.guild:
        try:
            invites = await invite.guild.invites()
            db_cache_invites(invite.guild.id, invites)
        except Exception:
            pass

@bot.event
async def on_member_join(member: discord.Member):
    guild_id = member.guild.id
    config = db_get_config(guild_id)
    invite_xp_amt = config.get("invite_xp", 25)
    try:
        current_invites = await member.guild.invites()
        inviter_id = db_find_used_invite(guild_id, current_invites)
        db_cache_invites(guild_id, current_invites)
        if inviter_id and invite_xp_amt > 0:
            # Apply double XP multiplier if active
            mult = db_has_double_xp(guild_id)
            xp_to_give = int(invite_xp_amt * mult)
            new_xp = db_add_xp(guild_id, inviter_id, xp_to_give)
            db_increment_stat(guild_id, inviter_id, "total_invites")
            # Assign monthly quests if needed
            month_key = current_month_key()
            db_assign_monthly_quests(guild_id, inviter_id, month_key)
            # Update quest progress
            newly_done = db_update_quest_progress(guild_id, inviter_id, "invite_members")
            await process_quest_completions(bot, guild_id, inviter_id, newly_done)
            # Check achievements
            await check_achievements(bot, guild_id, inviter_id)
            # Notify XP channel
            inviter = member.guild.get_member(inviter_id)
            name = inviter.display_name if inviter else f"<@{inviter_id}>"
            mult_str = f" (×{mult} Double XP!)" if mult > 1 else ""
            e = E("📨 New Invite!", color=C_INFO)
            e.description = (
                f"**{member.display_name}** joined!\n"
                f"Invited by: <@{inviter_id}>\n"
                f"Reward: **+{xp_to_give} XP**{mult_str}  |  Balance: **{new_xp} XP**"
            )
            await notify_xp(bot, guild_id, embed=e)
    except Exception as e:
        print(f"[Invite] Error on member join: {e}")

    # ── Welcome DM (on join) ────────────────────────────────────
    config = db_get_config(guild_id)
    if config.get("welcome_dm_enabled", 0):
        # Only DM if member has the required role (or no role restriction set)
        required_role_id = config.get("welcome_dm_role_id")
        if not required_role_id or any(r.id == required_role_id for r in member.roles):
            await send_welcome_dm(member, config)

    # ── Server welcome message (on join) ────────────────────────
    if config.get("server_welcome_enabled", 0):
        sw_ch_id = config.get("server_welcome_channel_id")
        if sw_ch_id:
            sw_ch = bot.get_channel(sw_ch_id)
            if sw_ch:
                info_ch = config.get("info_channel_id")
                info_str = f"<#{info_ch}>" if info_ch else "the info channel"
                try:
                    await sw_ch.send(
                        f"👋 Welcome to **{member.guild.name}**, {member.mention}! "
                        f"Check out {info_str} to learn how to earn XP and unlock rewards. 🎉"
                    )
                except Exception:
                    pass


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Track server boosts and role-based welcome DM."""
    guild_id = after.guild.id
    config = db_get_config(guild_id)

    # ── Detect new boost ────────────────────────────────────────
    if not before.premium_since and after.premium_since:
        boost_xp = config.get("boost_quest_xp", 100)
        if config.get("boost_quest_enabled", 1):
            new_xp = db_add_xp(guild_id, after.id, boost_xp)
            db_increment_stat(guild_id, after.id, "total_boosts")
            # Notify
            e = E("🚀 Server Boost!", color=C_ACHIEVE)
            e.description = (
                f"**{after.display_name}** boosted the server!\n"
                f"Reward: **+{boost_xp} XP**  |  Balance: **{new_xp} XP**"
            )
            await notify_xp(bot, guild_id, embed=e)
            # Quest / achievement check
            month_key = current_month_key()
            db_assign_monthly_quests(guild_id, after.id, month_key)
            await check_achievements(bot, guild_id, after.id)

    # ── Role-based welcome DM ───────────────────────────────────
    on_role_id = config.get("welcome_dm_on_role_id")
    if on_role_id and config.get("welcome_dm_enabled", 0):
        before_role_ids = {r.id for r in before.roles}
        after_role_ids  = {r.id for r in after.roles}
        if on_role_id in after_role_ids and on_role_id not in before_role_ids:
            await send_welcome_dm(after, config)

    # ── Role-based server welcome message ──────────────────────
    sw_on_role_id = config.get("server_welcome_on_role_id")
    if sw_on_role_id and config.get("server_welcome_enabled", 0):
        before_role_ids = {r.id for r in before.roles}
        after_role_ids  = {r.id for r in after.roles}
        if sw_on_role_id in after_role_ids and sw_on_role_id not in before_role_ids:
            sw_ch_id = config.get("server_welcome_channel_id")
            if sw_ch_id:
                sw_ch = bot.get_channel(sw_ch_id)
                if sw_ch:
                    info_ch = config.get("info_channel_id")
                    info_str = f"<#{info_ch}>" if info_ch else "the info channel"
                    try:
                        await sw_ch.send(
                            f"👋 Welcome, {after.mention}! "
                            f"Check out {info_str} to learn how to earn XP and unlock rewards. 🎉"
                        )
                    except Exception:
                        pass

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if not payload.guild_id:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    actor = guild.get_member(payload.user_id)
    if not actor or actor.bot:
        return
    config = db_get_config(payload.guild_id)
    if not config:
        return
    configured = config.get("reaction_emoji", "✅")
    emoji_str = (f"<:{payload.emoji.name}:{payload.emoji.id}>"
                 if payload.emoji.is_custom_emoji() else str(payload.emoji))
    if emoji_str != configured:
        return
    if not is_xp_manager(actor, config):
        return
    channel = bot.get_channel(payload.channel_id)
    if not channel:
        return
    try:
        message = await channel.fetch_message(payload.message_id)
    except Exception:
        return
    target = message.author
    if target.bot or target.id == actor.id:
        return
    if db_get_reaction_msg(payload.guild_id, payload.message_id):
        return
    react_xp   = config.get("reaction_xp", 50)
    cooldown_h = config.get("reaction_cooldown_h", 1)
    can_give, mins_left = db_reaction_cooldown_ok(payload.guild_id, target.id, cooldown_h)
    if not can_give:
        try:
            await channel.send(
                f"⏱️ {target.mention} must wait **{mins_left} min** before receiving reaction XP again.",
                delete_after=10)
        except Exception:
            pass
        return
    # Apply double XP multiplier
    mult = db_has_double_xp(payload.guild_id)
    xp_to_give = int(react_xp * mult)
    new_xp = db_add_xp(payload.guild_id, target.id, xp_to_give)
    db_set_reaction_cooldown(payload.guild_id, target.id)
    db_add_reaction_msg(payload.guild_id, payload.message_id, target.id, actor.id, xp_to_give)
    mult_str = f" (×{mult})" if mult > 1 else ""
    try:
        await channel.send(
            f"💎 {target.mention} received **+{xp_to_give} XP**{mult_str}! Total: **{new_xp} XP**",
            delete_after=15)
    except Exception:
        pass
    await check_achievements(bot, payload.guild_id, target.id)

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if not payload.guild_id:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    actor = guild.get_member(payload.user_id)
    if not actor or actor.bot:
        return
    config = db_get_config(payload.guild_id)
    if not config:
        return
    configured = config.get("reaction_emoji", "✅")
    emoji_str = (f"<:{payload.emoji.name}:{payload.emoji.id}>"
                 if payload.emoji.is_custom_emoji() else str(payload.emoji))
    if emoji_str != configured or not is_xp_manager(actor, config):
        return
    existing = db_get_reaction_msg(payload.guild_id, payload.message_id)
    if not existing:
        return
    target_id = existing["target_uid"]
    amount    = existing["amount"]
    new_xp    = db_add_xp(payload.guild_id, target_id, -amount)
    db_remove_reaction_msg(payload.guild_id, payload.message_id)
    channel = bot.get_channel(payload.channel_id)
    if channel:
        try:
            await channel.send(
                f"⚠️ <@{target_id}> lost **{amount} XP** (reaction removed). Total: **{max(0, new_xp)} XP**",
                delete_after=15)
        except Exception:
            pass

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return
    config = db_get_config(message.guild.id)
    share_ch_id = config.get("share_channel_id")
    if share_ch_id and message.channel.id == share_ch_id:
        await _handle_share(message, config)
    await bot.process_commands(message)

async def _handle_share(message: discord.Message, config: dict):
    guild_id   = message.guild.id
    window_min = config.get("share_window_min") or 20
    video_id   = extract_video_id(message.content)
    if not video_id:
        return  # No YouTube link — ignore

    # Require at least one image attachment (screenshot)
    has_image = any(
        att.content_type and att.content_type.startswith("image/")
        for att in message.attachments
    ) if message.attachments else False

    if not has_image:
        try:
            await message.reply(
                "📸 Don't forget to attach a **screenshot of your comment**!", delete_after=20)
        except Exception:
            pass
        return

    current = db_get_current_video(guild_id)
    if not current:
        try:
            await message.reply("⚠️ No active video right now. Wait for the next one!", delete_after=20)
        except Exception:
            pass
        return

    # Check share window
    try:
        detected_at = datetime.fromisoformat(current["detected_at"])
        deadline = detected_at + timedelta(minutes=window_min)
        if datetime.utcnow() > deadline:
            deadline_ts = int(deadline.timestamp())
            try:
                await message.reply(
                    f"⏰ Share window closed <t:{deadline_ts}:R>. Wait for the next video!",
                    delete_after=30)
            except Exception:
                pass
            return
    except Exception:
        pass

    # Check video match
    if video_id != current["video_id"]:
        try:
            await message.reply(
                f"❌ Link doesn't match the current video.\n"
                f"📲 [Short]({make_shorts_url(current['video_id'])})  •  🖥️ [Watch]({make_watch_url(current['video_id'])})",
                delete_after=30)
        except Exception:
            pass
        return

    # Already shared?
    if db_has_shared(guild_id, video_id, message.author.id):
        try:
            await message.reply("✅ You already shared this video! Wait for the next one.", delete_after=20)
        except Exception:
            pass
        return

    # ── All checks passed — award XP automatically ──
    position = db_add_share(guild_id, video_id, message.author.id)
    db_increment_stat(guild_id, message.author.id, "total_shares")

    # Apply Double XP multiplier
    mult = db_has_double_xp(guild_id)

    # Streak bonus
    streak_info = db_get_streak(guild_id, message.author.id)
    prev_video_id = current.get("previous_video_id")
    if config.get("streak_enabled", 1):
        if prev_video_id and streak_info["last_video_id"] == prev_video_id:
            new_streak = streak_info["current_streak"] + 1
        else:
            new_streak = 1
    else:
        new_streak = 0

    streak_bonus = 0
    if config.get("streak_enabled", 1) and new_streak > 0:
        bonus_per = config.get("streak_xp_bonus", 2)
        cap       = config.get("streak_xp_cap", 30)
        streak_bonus = min(new_streak * bonus_per, cap)

    # Base XP — there's no separate share_xp config since managers control final validation,
    # so we use reaction_xp as a reference. Award reaction_xp for the share.
    # (Note: share XP is now the reaction_xp value since auto-attribution replaced manual)
    # We add a dedicated share_xp column check — defaults from guild config
    # Retrieve from config; if missing, default 100
    share_xp_base = config.get("reaction_xp", 50)  # video share XP = reaction XP

    total_xp = int((share_xp_base + streak_bonus) * mult)
    new_xp = db_add_xp(guild_id, message.author.id, total_xp)

    # Update streak
    if config.get("streak_enabled", 1):
        max_streak = db_update_streak(guild_id, message.author.id, new_streak, video_id)
        db_update_max_streak_stat(guild_id, message.author.id, new_streak)
        await update_streak_nickname(message.guild, message.author.id, new_streak)

    # Confirm to member
    parts = [f"✅ {message.author.mention} — **+{total_xp} XP**! Balance: **{new_xp} XP**"]
    if config.get("streak_enabled", 1) and new_streak > 0:
        parts.append(f"🔥 Streak: **{new_streak}**" + (f" (+{streak_bonus} XP bonus)" if streak_bonus else ""))
    if mult > 1:
        parts.append(f"⚡ Double XP active! (×{mult})")
    if position <= 5:
        parts.append(f"🥇 You're #{position} to share this video!")
    try:
        await message.reply("\n".join(parts), delete_after=30)
    except Exception:
        pass

    # Update quests
    month_key = current_month_key()
    db_assign_monthly_quests(guild_id, message.author.id, month_key)
    newly_done = db_update_quest_progress(guild_id, message.author.id, "share_videos")
    # Streak quest
    if config.get("streak_enabled", 1):
        newly_done += db_update_quest_progress(guild_id, message.author.id, "video_streak",
                                               value=new_streak)
    # First 5 quest
    if position <= 5:
        newly_done += db_update_quest_progress(guild_id, message.author.id, "first_5")
    # #1 quest
    if position == 1:
        newly_done += db_update_quest_progress(guild_id, message.author.id, "top_1")
    await process_quest_completions(bot, guild_id, message.author.id, newly_done)
    # Community goal contributions
    active_goals = db_get_community_goals(guild_id)
    for goal in active_goals:
        if goal["goal_type"] == "share_videos" and not goal["completed"]:
            updated = db_add_goal_contribution(guild_id, goal["id"], message.author.id)
            if updated.get("completed") and not goal["completed"]:
                # Already handled by check_community_goals background task
                pass
    # Achievements
    await check_achievements(bot, guild_id, message.author.id)

# ══════════════════════════════════════════════════════════════
#  SLASH COMMANDS
# ══════════════════════════════════════════════════════════════

async def _check_commands_channel(interaction: discord.Interaction) -> bool:
    """Returns True if the interaction is in the configured commands channel (or not configured)."""
    config = db_get_config(interaction.guild_id)
    ch_id = config.get("commands_channel_id")
    if not ch_id:
        return True
    if interaction.channel_id != ch_id:
        await interaction.response.send_message(
            f"❌ Please use <#{ch_id}> for bot commands.", ephemeral=True)
        return False
    return True

# ── /config ───────────────────────────────────────────────────

@bot.tree.command(name="config", description="⚙️ Open the bot configuration panel")
async def cmd_config(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    if not isinstance(interaction.user, discord.Member):
        return
    db_ensure_config(interaction.guild_id)
    config = db_get_config(interaction.guild_id)
    if not is_xp_manager(interaction.user, config):
        await interaction.response.send_message("❌ You need the **XP Manager** role.", ephemeral=True)
        return
    view  = ConfigMainMenu(interaction.guild, interaction.user.id)
    embed = config_overview_embed(interaction.guild, config)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ── /admin ────────────────────────────────────────────────────

@bot.tree.command(name="admin", description="🛠️ Open the admin panel")
async def cmd_admin(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    if not isinstance(interaction.user, discord.Member):
        return
    config = db_get_config(interaction.guild_id)
    if not is_xp_manager(interaction.user, config):
        await interaction.response.send_message("❌ You need the **XP Manager** role.", ephemeral=True)
        return
    view = AdminMainMenu(interaction.guild, interaction.user.id)
    await interaction.response.send_message(embed=admin_main_embed(interaction.guild), view=view, ephemeral=True)

# ── /xp ──────────────────────────────────────────────────────

@bot.tree.command(name="xp", description="💰 Check your XP balance and rank")
@app_commands.describe(member="Check another member's XP (XP Managers only)")
async def cmd_xp(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    if not interaction.guild:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    if not await _check_commands_channel(interaction):
        return
    config = db_get_config(interaction.guild_id)
    if member and member.id != interaction.user.id:
        if not isinstance(interaction.user, discord.Member) or not is_xp_manager(interaction.user, config):
            await interaction.response.send_message("❌ Only XP Managers can view others' XP.", ephemeral=True)
            return
        target = member
    else:
        target = interaction.user

    xp   = db_get_xp(interaction.guild_id, target.id)
    top  = db_top_xp(interaction.guild_id, limit=1000)
    rank = next((i+1 for i, (uid, _) in enumerate(top) if uid == target.id), None)
    streak = db_get_streak(interaction.guild_id, target.id)

    e = E(color=C_GOLD)
    e.set_author(name=str(target), icon_url=target.display_avatar.url if target.display_avatar else None)
    e.add_field(name="💰 XP",       value=f"**{xp} XP**",                            inline=True)
    if rank:
        e.add_field(name="🏆 Rank", value=f"**#{rank}**",                             inline=True)
    if config.get("streak_enabled", 1):
        e.add_field(name="🔥 Streak",value=f"**{streak['current_streak']}**"
                    + (f" (max: {streak['max_streak']})" if streak["max_streak"] else ""), inline=True)
    await interaction.response.send_message(embed=e)

# ── /leaderboard ─────────────────────────────────────────────

@bot.tree.command(name="leaderboard", description="🏆 Top XP leaderboard")
@app_commands.describe(limit="How many members to show (max 25, default 10)")
async def cmd_leaderboard(interaction: discord.Interaction, limit: int = 10):
    if not interaction.guild:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    if not await _check_commands_channel(interaction):
        return
    limit = max(1, min(25, limit))
    await interaction.response.defer()
    top = db_top_xp(interaction.guild_id, limit=limit)
    if not top:
        await interaction.followup.send("❌ Nobody has earned XP yet!")
        return
    medals = ["🥇", "🥈", "🥉"]
    lines  = []
    for i, (uid, xp) in enumerate(top):
        prefix = medals[i] if i < 3 else f"`{i+1}.`"
        try:
            user = await bot.fetch_user(uid)
            name = user.display_name
        except Exception:
            name = f"Unknown ({uid})"
        streak = db_get_streak(interaction.guild_id, uid)
        streak_str = f" 🔥{streak['current_streak']}" if streak["current_streak"] > 0 else ""
        lines.append(f"{prefix} **{name}**{streak_str} — {xp} XP")
    e = E(f"🏆 XP Leaderboard — Top {limit}", "\n".join(lines), C_GOLD)
    await interaction.followup.send(embed=e)

# ── /shop ─────────────────────────────────────────────────────

@bot.tree.command(name="shop", description="🛒 Browse and buy items with your XP")
async def cmd_shop(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    if not await _check_commands_channel(interaction):
        return
    if not isinstance(interaction.user, discord.Member):
        return
    view = ShopView(interaction.guild, interaction.user)
    await interaction.response.send_message(embed=view.embed(), view=view)

# ── /inventory ────────────────────────────────────────────────

@bot.tree.command(name="inventory", description="🎒 View your purchased items")
@app_commands.describe(member="View another member's inventory (XP Managers only)")
async def cmd_inventory(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    if not interaction.guild:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    if not await _check_commands_channel(interaction):
        return
    config = db_get_config(interaction.guild_id)
    if member and member.id != interaction.user.id:
        if not isinstance(interaction.user, discord.Member) or not is_xp_manager(interaction.user, config):
            await interaction.response.send_message("❌ Only XP Managers can view others' inventories.", ephemeral=True)
            return
        target = member
    else:
        target = interaction.user

    items = db_get_inventory(interaction.guild_id, target.id)
    e = E(f"🎒 Inventory — {target.display_name}", color=C_INFO)
    if not items:
        e.description = "Your inventory is empty. Buy items from `/shop`!"
    else:
        for item in items:
            if item["is_expired"]:
                name = f"~~{item['item_name']}~~ *(expired)*"
            elif item.get("expires_at"):
                try:
                    exp = datetime.fromisoformat(item["expires_at"])
                    days_left = (exp - datetime.now()).days
                    name = f"{item['item_name']} *(expires in {days_left}d)*"
                except Exception:
                    name = item["item_name"]
            else:
                name = item["item_name"]
            e.add_field(name=name, value=f"Purchased: {item.get('purchased_at', '?')[:10]}", inline=True)
    await interaction.response.send_message(embed=e)

# ── /video ────────────────────────────────────────────────────

@bot.tree.command(name="video", description="🎬 See the current video to share for XP")
async def cmd_video(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    if not await _check_commands_channel(interaction):
        return
    current = db_get_current_video(interaction.guild_id)
    if not current:
        await interaction.response.send_message("⚠️ No active video right now.", ephemeral=True)
        return
    config = db_get_config(interaction.guild_id)
    already_shared = db_has_shared(interaction.guild_id, current["video_id"], interaction.user.id)
    e = E(
        "🎬 Current Video",
        f"**{current['video_title']}**\n\n"
        f"📲 [Short]({make_shorts_url(current['video_id'])})  •  🖥️ [Watch]({make_watch_url(current['video_id'])})",
        color=C_GOLD
    )
    if already_shared:
        e.add_field(name="✅ Already shared", value="You shared this one — wait for the next!", inline=False)
    else:
        share_ch = config.get("share_channel_id")
        e.add_field(
            name="🎁 How to earn XP",
            value=f"Share the link + screenshot in <#{share_ch}>" if share_ch else "Set a share channel with `/config`",
            inline=False
        )
    if config.get("streak_enabled", 1):
        streak = db_get_streak(interaction.guild_id, interaction.user.id)
        e.add_field(name="🔥 Your streak", value=f"**{streak['current_streak']}**", inline=True)
    await interaction.response.send_message(embed=e)

# ── /quests ───────────────────────────────────────────────────

@bot.tree.command(name="quests", description="📅 View your monthly quests")
async def cmd_quests(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    if not await _check_commands_channel(interaction):
        return
    guild_id  = interaction.guild_id
    user_id   = interaction.user.id
    month_key = current_month_key()
    db_assign_monthly_quests(guild_id, user_id, month_key)
    quests = db_get_user_quests(guild_id, user_id, month_key)
    config = db_get_config(guild_id)
    xp_map = {
        "stone": config.get("quest_xp_stone", 50),
        "bronze": config.get("quest_xp_bronze", 100),
        "silver": config.get("quest_xp_silver", 200),
        "gold": config.get("quest_xp_gold", 400),
        "diamond": config.get("quest_xp_diamond", 750),
    }
    e = E(f"📅 Monthly Quests — {month_key}", color=C_QUEST)
    e.set_author(name=str(interaction.user),
                 icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)
    for rarity in RARITIES:
        quest = next((q for q in quests if q["rarity"] == rarity), None)
        if not quest:
            e.add_field(name=f"{RARITY_EMOJI[rarity]} {rarity.capitalize()}", value="`Not assigned yet`", inline=False)
            continue
        progress_pct = min(quest["progress"] / quest["quest_target"], 1.0) if quest["quest_target"] else 1.0
        bar_filled = int(progress_pct * 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        status = "✅ **COMPLETE**" if quest["completed"] else f"`{bar}` {quest['progress']}/{quest['quest_target']}"
        reward_str = f"**{xp_map.get(rarity, 50)} XP**" + (" *(claimed)*" if quest.get("xp_awarded") else "")
        e.add_field(
            name=f"{RARITY_EMOJI[rarity]} {rarity.capitalize()} — {quest['quest_name']}",
            value=f"{status}\nReward: {reward_str}",
            inline=False
        )
    # Boost quest
    if config.get("boost_quest_enabled", 1):
        e.add_field(
            name="🚀 Boost Quest (Repeatable)",
            value=f"Boost the server → **+{config.get('boost_quest_xp', 100)} XP** per boost\n♾️ Unlimited completions",
            inline=False
        )
    await interaction.response.send_message(embed=e)

# ── /achievements ─────────────────────────────────────────────

@bot.tree.command(name="achievements", description="🏆 View your achievements")
@app_commands.describe(member="View another member's achievements")
async def cmd_achievements(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    if not interaction.guild:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    if not await _check_commands_channel(interaction):
        return
    guild_id = interaction.guild_id
    target = member or interaction.user
    db_ensure_achievement_config(guild_id)
    stats = db_get_stats(guild_id, target.id)
    conn = get_db()
    unlocked_rows = conn.execute(
        "SELECT achievement_key, tier FROM achievements WHERE guild_id=? AND user_id=?",
        (guild_id, target.id)
    ).fetchall()
    conn.close()
    unlocked = {(r["achievement_key"], r["tier"]) for r in unlocked_rows}
    e = E(f"🏆 Achievements — {target.display_name}", color=C_ACHIEVE)
    e.set_author(name=str(target), icon_url=target.display_avatar.url if target.display_avatar else None)
    tier_names = ["I", "II", "III", "IV", "V"]
    for ach_def in ACHIEVEMENT_DEFS:
        tiers = db_get_achievement_config(guild_id, ach_def["key"])
        if not tiers:
            tiers = [{"tier": i, "threshold": t, "role_id": None, "enabled": 1}
                     for i, t in enumerate(ach_def["tiers"])]
        stat_val = stats.get(ach_def["category"], 0)
        tier_strs = []
        for t in tiers:
            if not t.get("enabled", 1):
                continue
            tier_idx = t["tier"]
            tier_label = tier_names[tier_idx] if tier_idx < len(tier_names) else str(tier_idx)
            unlocked_icon = "✅" if (ach_def["key"], tier_idx) in unlocked else "🔒"
            tier_strs.append(f"{unlocked_icon} {tier_label}: {t['threshold']}")
        e.add_field(
            name=f"{ach_def['name']}  (current: {stat_val})",
            value="  ".join(tier_strs) if tier_strs else "`No tiers configured`",
            inline=False
        )
    await interaction.response.send_message(embed=e)

# ── /info ─────────────────────────────────────────────────────

@bot.tree.command(name="info", description="ℹ️ How does the XP system work?")
async def cmd_info(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ Server only.", ephemeral=True)
        return
    if not await _check_commands_channel(interaction):
        return
    config = db_get_config(interaction.guild_id)
    e = E("📖 XP System — How it works", color=C_INFO)
    # Share
    share_ch = config.get("share_channel_id")
    e.add_field(
        name="🎬 Video Share",
        value=("When a new video drops, share the link + a screenshot of your comment in "
               + (f"<#{share_ch}>" if share_ch else "the share channel")
               + " → XP awarded instantly.\n_(Once per video per member)_"),
        inline=False
    )
    # Reaction
    emoji = config.get("reaction_emoji", "✅")
    e.add_field(
        name=f"{emoji} Reaction XP",
        value=f"An XP Manager reacts with {emoji} on any message → **+{config.get('reaction_xp', 50)} XP**",
        inline=False
    )
    # Invites
    e.add_field(
        name="📨 Invites",
        value=f"Invite a member → **+{config.get('invite_xp', 25)} XP**",
        inline=False
    )
    # Streak
    if config.get("streak_enabled", 1):
        e.add_field(
            name="🔥 Video Streak",
            value=(f"Support consecutive videos to build a streak.\n"
                   f"Bonus: up to **+{config.get('streak_xp_cap', 30)} XP** per share.\n"
                   f"Streak shown in your nickname as 🔥N."),
            inline=False
        )
    # Boost
    if config.get("boost_quest_enabled", 1):
        e.add_field(
            name="🚀 Server Boost",
            value=f"Boost the server → **+{config.get('boost_quest_xp', 100)} XP** (repeatable)",
            inline=False
        )
    # Commands
    cmds_ch = config.get("commands_channel_id")
    e.add_field(
        name="📋 Commands" + (f" (use in <#{cmds_ch}>)" if cmds_ch else ""),
        value=(
            "`/xp` — XP balance & rank\n"
            "`/leaderboard` — Server ranking\n"
            "`/shop` — Buy items with XP\n"
            "`/inventory` — Your items\n"
            "`/quests` — Monthly quests\n"
            "`/achievements` — Your achievements\n"
            "`/video` — Current video to share"
        ),
        inline=False
    )
    await interaction.response.send_message(embed=e)

# ── Error handler ─────────────────────────────────────────────

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print(f"[Slash error] {error}")
    msg = "❌ Something went wrong. Please try again."
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════
#  SHARE XP migration — add share_xp column if missing
# ══════════════════════════════════════════════════════════════

def _add_share_xp_column():
    try:
        conn = get_db()
        conn.execute("ALTER TABLE guild_config ADD COLUMN share_xp INTEGER DEFAULT 100")
        conn.commit()
        conn.close()
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════
#  FLASK — keep-alive
# ══════════════════════════════════════════════════════════════

flask_app = Flask('')

@flask_app.route('/')
def home():
    return "Bot is alive!"

@flask_app.route('/health')
def health():
    return {"status": "ok", "bot": str(bot.user) if bot.user else "Not connected"}

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

def keep_alive():
    Thread(target=run_flask, daemon=True).start()

# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    _add_share_xp_column()
    init_db()
    keep_alive()
    token = os.environ.get("TOKEN")
    if not token:
        print("❌ Missing TOKEN environment variable!")
        exit(1)
    bot.run(token)
