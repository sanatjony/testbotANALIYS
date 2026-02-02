# --- faqat o‘zgargan va yetishmayotgan joylar ko‘rsatilmaydi ---
# BU TO‘LIQ FAYL. OLDINGI FUNKSIYALAR SAQLANGAN.

import asyncio, re, sqlite3, time, os, requests
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command

BOT_TOKEN = os.getenv("BOT_TOKEN").strip()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEYS").strip()

CREDIT_DAILY = 5
TTL_VIDEO = 6*3600
TTL_SEARCH = 12*3600
TTL_CHANNEL = 24*3600

# ================= DB =================
conn = sqlite3.connect("bot.db")
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    title TEXT, channel TEXT, channel_id TEXT,
    category TEXT, published TEXT,
    views INTEGER, likes INTEGER, comments INTEGER,
    tags TEXT, description TEXT, updated_at INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS search_cache (
    query TEXT, type TEXT, result TEXT, updated_at INTEGER,
    PRIMARY KEY (query, type)
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS channel_cache (
    channel_id TEXT PRIMARY KEY, keywords TEXT, updated_at INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY, credit INTEGER, last_reset INTEGER
)""")

conn.commit()
# =====================================

def yt_api(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(f"https://www.googleapis.com/youtube/v3/{endpoint}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def extract_video_id(url):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m: return m.group(1)
    return None

def get_credit(uid):
    now = int(time.time())
    cur.execute("SELECT credit, last_reset FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users VALUES (?,?,?)", (uid, CREDIT_DAILY, now))
        conn.commit()
        return CREDIT_DAILY
    credit, last = row
    if now-last >= 86400:
        credit = CREDIT_DAILY
        cur.execute("UPDATE users SET credit=?, last_reset=?", (credit, now))
        conn.commit()
    return credit

def use_credit(uid):
    cur.execute("UPDATE users SET credit=credit-1 WHERE user_id=?", (uid,))
    conn.commit()

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

def result_kb(vid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🧠 TOP 10 KONKURENT VIDEO", callback_data=f"top:{vid}")],
        [InlineKeyboardButton("📺 RAQOBATCHI KANALLAR", callback_data=f"channels:{vid}")],
        [InlineKeyboardButton("🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")]
    ])

# ================= KONKURENT VIDEOLAR =================
@dp.callback_query(F.data.startswith("top:"))
async def top_videos(c: CallbackQuery):
    vid = c.data.split(":")[1]
    cur.execute("SELECT title FROM videos WHERE video_id=?", (vid,))
    title = cur.fetchone()[0]

    now = int(time.time())
    cur.execute("SELECT result, updated_at FROM search_cache WHERE query=? AND type='video'", (title,))
    row = cur.fetchone()

    if row and now-row[1] < TTL_SEARCH:
        result = row[0]
    else:
        data = yt_api("search", {
            "part": "snippet",
            "type": "video",
            "order": "viewCount",
            "maxResults": 10,
            "publishedAfter": (datetime.utcnow()-timedelta(days=30)).isoformat()+"Z",
            "q": title
        })
        lines = []
        for i, it in enumerate(data.get("items", [])[:10], 1):
            v_id = it["id"]["videoId"]
            v_title = it["snippet"]["title"]
            lines.append(f"{i}. {v_title}\nhttps://youtu.be/{v_id}")
        result = "\n\n".join(lines)
        cur.execute("INSERT OR REPLACE INTO search_cache VALUES (?,?,?,?)",
                    (title, "video", result, now))
        conn.commit()

    await c.message.answer("🧠 TOP 10 KONKURENT VIDEO (30 kun):\n\n"+result)
    await c.answer()

# ================= RAQOBATCHI KANALLAR =================
@dp.callback_query(F.data.startswith("channels:"))
async def channels(c: CallbackQuery):
    vid = c.data.split(":")[1]
    cur.execute("SELECT title FROM videos WHERE video_id=?", (vid,))
    title = cur.fetchone()[0]

    data = yt_api("search", {
        "part": "snippet",
        "type": "channel",
        "maxResults": 5,
        "q": title
    })

    text = "📺 RAQOBATCHI KANALLAR (TOP 5):\n\n"
    for i, it in enumerate(data.get("items", [])[:5], 1):
        cid = it["id"]["channelId"]
        name = it["snippet"]["channelTitle"]
        text += f"{i}. {name} — https://www.youtube.com/channel/{cid}\n"

    await c.message.answer(text)
    await c.answer()

# ================= TAG / TAVSIF =================
@dp.callback_query(F.data.startswith("tags:"))
async def tags(c: CallbackQuery):
    vid = c.data.split(":")[1]
    cur.execute("SELECT tags, description, channel_id FROM videos WHERE video_id=?", (vid,))
    v_tags, desc, channel_id = cur.fetchone()

    data = yt_api("channels", {"part": "brandingSettings", "id": channel_id})
    ch_tags = data["items"][0]["brandingSettings"]["channel"].get("keywords", "")

    await c.message.answer(
        f"🏷 VIDEO TAGLAR:\n```\n{v_tags}\n```\n\n"
        f"🏷 KANAL TAGLAR:\n```\n{ch_tags}\n```\n\n"
        f"📝 DESCRIPTION:\n```\n{desc[:3500]}\n```",
        parse_mode="Markdown"
    )
    await c.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
