# Discord XP Bot v2

Multi-server XP bot — fully button-driven, zero hardcoded IDs.

---

## Features

| Feature | Description |
|---------|-------------|
| 🎬 Video Share XP | Auto-validated (link + screenshot). XP awarded instantly. |
| ✅ Reaction XP | XP Manager reacts with configured emoji → member earns XP |
| 📨 Invite XP | Inviting a member earns configurable XP |
| 🔥 Video Streak | Consecutive supports build a streak shown in nickname (🔥N) |
| 📅 Monthly Quests | 5 rarities (Stone → Diamond), random quest per user per month |
| 🚀 Boost Quest | Nitro Boost = XP, repeatable, configurable |
| 🏆 Achievements | Discord role rewards, fully configurable thresholds |
| 🎉 Events | Double XP events, Community Goals |
| 🛒 Shop | Images, temporary items (expired label), text-input items |
| 💾 Backup | Auto every 15 min to configured Discord channel |

---

## Files

| File | Purpose |
|------|---------|
| `main.py` | Bot source code |
| `requirements.txt` | Python dependencies |
| `Procfile` | Render start command |
| `.gitignore` | Prevents committing the database |

---

## Deploy on Render

### 1. Push these files to a GitHub repository

```
your-repo/
├── main.py
├── requirements.txt
├── Procfile
├── .gitignore
└── README.md
```

### 2. Create a Render service

1. Go to [render.com](https://render.com) → **New** → **Worker**
2. Connect your GitHub repository
3. Configure:
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`

### 3. Add environment variable

| Key | Value |
|-----|-------|
| `TOKEN` | Your Discord bot token |

---

## Discord Developer Portal Setup

### Required intents

Go to [discord.com/developers](https://discord.com/developers/applications) → your app → **Bot**:

- ✅ **SERVER MEMBERS INTENT**
- ✅ **MESSAGE CONTENT INTENT**

### Required permissions

- Read Messages / View Channels
- Send Messages
- Embed Links
- Add Reactions
- Read Message History
- Manage Messages
- **Manage Nicknames** ← Required for streak display in nicknames

### ⚠️ Streak nickname — role hierarchy

For the bot to update member nicknames (streak display), its role must be **above** the member's highest role in the server's role list. The bot **cannot** change the nickname of anyone with an equal or higher role.

**Invite URL scope:** `bot` + `applications.commands`

---

## First-time setup

Once the bot is online, use `/config` to configure everything:

```
/config
 ├── 📺 YouTube     → Set YouTube channel to watch for new videos
 ├── 💬 Channels    → Share / Notifications / Commands / Admin / Log / Backup channels
 ├── 💰 XP & Invites → XP amounts, emoji, cooldown, invite XP, share window
 ├── 🔥 Streak      → Enable/disable, bonus per level, cap, reset on miss
 ├── 🛒 Shop        → Add/remove items (images, temporary, text-input)
 ├── 📅 Quests      → XP per rarity, boost quest, enable/disable individual quests
 ├── 🏆 Achievements→ Thresholds, Discord roles, announcement channel
 ├── 🎉 Events      → Double XP events, Community Goals
 ├── 👥 Permissions → XP Manager role
 └── 📊 Status      → Overview + health check
```

> **First run:** if no XP Manager role is set, any Discord administrator can open `/config`.
> Once you assign a role, only holders of that role can manage the bot.

---

## Commands

### Member commands (restricted to configured commands channel)

| Command | Description |
|---------|-------------|
| `/xp` | Check XP balance, rank, and streak |
| `/leaderboard` | Server XP top list |
| `/shop` | Browse and buy items |
| `/inventory` | View purchased items (expired items shown as ~~expired~~) |
| `/video` | See the current video to share |
| `/quests` | View monthly quests + boost quest |
| `/achievements` | View unlocked achievements |
| `/info` | How the XP system works |

### Manager commands (usable anywhere)

| Command | Description |
|---------|-------------|
| `/config` | Full configuration panel |
| `/admin` | Manage XP, shop, streaks, backups, stats, community goals |

---

## How XP is earned

### 🎬 Video share (auto)
1. Bot polls YouTube RSS every **60 seconds**
2. New video detected → ping in share channel with countdown
3. Member posts link + screenshot → XP awarded instantly
4. _(Managers can remove XP via `/admin` if screenshot is invalid)_

### ✅ Reaction XP (bonus)
1. XP Manager reacts with configured emoji on any message
2. Message author gets XP instantly
3. Removing the reaction takes XP back

### 📨 Invite XP
- When someone joins via your invite link → you earn configurable XP

### 🔥 Video Streak
- Streak +1 for each consecutive video supported
- Missing a video resets streak (configurable)
- Bonus XP = min(streak × bonus_per_level, cap)
- Nickname updated automatically: `username 🔥15`

### 🚀 Server Boost
- Boosting the server earns configurable XP (repeatable)

---

## Monthly Quests

Each user receives exactly 5 random quests per month (one per rarity):

| Rarity | Default XP |
|--------|-----------|
| 🪨 Stone | 50 XP |
| 🥉 Bronze | 100 XP |
| 🥈 Silver | 200 XP |
| 🥇 Gold | 400 XP |
| 💎 Diamond | 750 XP |

All XP amounts and quest pools are configurable in `/config → 📅 Quests`.

---

## Achievements

Achievements grant **Discord roles only** (no XP).

| Achievement | Tracks |
|------------|--------|
| Video Supporter | Total video shares |
| Recruiter | Total invites |
| On Fire | Max streak ever reached |
| Server Booster | Total server boosts |
| Quest Master | Total monthly quests completed |

Each has 5 tiers (I–V) with configurable thresholds and roles.

---

## Events

- **Double XP** — multiplies all XP gains for the event duration (streak bonus excluded)
- **Community Goal** — server-wide target (e.g. 100 shares); contributors earn reward XP when goal is reached

---

## Shop

Items support:
- 🖼️ **Image URL** — shown as thumbnail in `/shop`
- ⏳ **Temporary** — expires after N days; item stays in inventory marked as ~~expired~~
- 📝 **Text input** — buyer must enter text (e.g. game username) after purchase → sent privately to admin channel

---

## Database

SQLite (`bot_data.db`) stored on the Render instance.

> ⚠️ Render's free tier has **ephemeral storage** — the DB is wiped on restart.
> Configure a **Backup Channel** in `/config → 💬 Channels`.
> The bot sends the DB there every 15 minutes and restores it on startup.

For persistent storage, upgrade to a paid Render plan with a persistent disk,
or migrate to a hosted DB (Supabase, PlanetScale) and adapt the DB layer.
