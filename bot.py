import asyncio
import re
import sqlite3
import time
import os
import requests
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEYS")

if not BOT_TOKEN or not YOUTUBE_API_KEY:
    raise RuntimeError("ENV yo‘q")

BOT_TOKEN = BOT_TOKEN.strip()
YOUTUBE_API_KEY = YOUTUBE_API_KEY.strip()
# =====================================


# ================= CONFIG ==============
CREDIT_DAILY = 5
TTL_VIDEO = 6 * 3600
TTL_SEARCH = 12 * 3600
TTL_CHANNEL = 24 * 3600
# =====================================


# ================= DATABASE ============
conn = sqlite3.connect("bot.db")
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    credit INTEGER,
    last_reset INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    title TEXT,
    channel TEXT,
    channel_id TEXT,
    category TEXT,
    published TEXT,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    tags TEXT,
    description TEXT,
    updated_at INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS search_cache (
    query TEXT,
    type TEXT,
    result TEXT,
    updated_at INTEGER,
    PRIMARY KEY (query, type)
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS categories (
    category_id TEXT PRIMARY KEY,
    name TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS channel_cache (
    channel_id TEXT PRIMARY KEY,
    keywords TEXT,
    updated_at INTEGER
)""")

conn.commit()
# =====================================


# ================= HELPERS =============
YOUTUBE_REGEX = r"(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+)"

def extract_video_id(url):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def yt_api(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=20
    )
    r.raise_for_status()
    return r.json()

def split_text(text, limit=4000):
    return [text[i:i+limit] for i in range(0, len(text), limit)]
# =====================================


# ================= CATEGORY ============
def preload_categories():
    cur.execute("SELECT COUNT(*) FROM categories")
    if cur.fetchone()[0] > 0:
        return
    data = yt_api("videoCategories", {"part": "snippet", "regionCode": "US"})
    for it in data.get("items", []):
        cur.execute(
            "INSERT OR IGNORE INTO categories VALUES (?,?)",
            (it["id"], it["snippet"]["title"])
        )
    conn.commit()

def resolve_category(cat_id):
    if not cat_id:
        return "Unknown"
    cur.execute("SELECT name FROM categories WHERE category_id=?", (cat_id,))
    row = cur.fetchone()
    return row[0] if row else "Unknown"
# =====================================


# ================= CREDIT ==============
def get_credit(uid):
    now = int(time.time())
    cur.execute("SELECT credit, last_reset FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users VALUES (?,?,?)", (uid, CREDIT_DAILY, now))
        conn.commit()
        return CREDIT_DAILY
    credit, last = row
    if now - last >= 86400:
        credit = CREDIT_DAILY
        cur.execute("UPDATE users SET credit=?, last_reset=? WHERE user_id=?",
                    (credit, now, uid))
        conn.commit()
    return credit

def use_credit(uid):
    cur.execute("UPDATE users SET credit=credit-1 WHERE user_id=?", (uid,))
    conn.commit()
# =====================================


# ================= FRAUD ===============
def detect_like_fraud(views, likes, comments, hours):
    if views == 0:
        return "⚪ Ma’lumot yetarli emas"
    if likes / views > 0.25 and views > 1000:
        return "🔴 LIKE NAKRUTKA EHTIMOLI"
    if comments / views < 0.001 and views > 5000:
        return "🟡 SHUBHALI FAOLLIGI"
    if hours < 2 and views > 10000:
        return "🟡 TEZ SUN’IY O‘SISH"
    return "🟢 NORMAL FAOLLIGI"
# =====================================


bot = Bot(BOT_TOKEN)
dp = Dispatcher()


def result_kb(vid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 TOP 10 KONKURENT VIDEO", callback_data=f"top:{vid}")],
        [InlineKeyboardButton(text="📺 RAQOBATCHI KANALLAR", callback_data=f"channels:{vid}")],
        [InlineKeyboardButton(text="🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")]
    ])


@dp.message(Command("start"))
async def start(m: Message):
    preload_categories()
    credit = get_credit(m.from_user.id)
    await m.answer(
        "👋 YouTube ANALIZ BOT\n\n👉 YouTube linkni yuboring\n"
        f"💳 Kredit: {credit}/{CREDIT_DAILY}"
    )


@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def analyze(m: Message):
    uid = m.from_user.id
    credit = get_credit(uid)

    vid = extract_video_id(m.text)
    if not vid:
        return

    data = yt_api("videos", {"part": "snippet,statistics", "id": vid})
    it = data["items"][0]
    sn, st = it["snippet"], it["statistics"]

    category = resolve_category(sn.get("categoryId"))

    cur.execute("""
        INSERT OR REPLACE INTO videos
        (video_id,title,channel,channel_id,category,published,
         views,likes,comments,tags,description,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        vid, sn["title"], sn["channelTitle"], sn["channelId"], category,
        sn["publishedAt"], int(st.get("viewCount",0)), int(st.get("likeCount",0)),
        int(st.get("commentCount",0)), ", ".join(sn.get("tags",[])),
        sn.get("description",""), int(time.time())
    ))
    conn.commit()

    dt = datetime.fromisoformat(sn["publishedAt"].replace("Z","+00:00"))
    hours = (datetime.now(timezone.utc) - dt).total_seconds()/3600
    fraud = detect_like_fraud(int(st.get("viewCount",0)), int(st.get("likeCount",0)),
                              int(st.get("commentCount",0)), hours)

    await m.answer(
        f"🎬 {sn['title']}\n"
        f"📂 Kategoriya: {category}\n"
        f"📺 Kanal: {sn['channelTitle']}\n"
        f"⏰ Yuklangan: {dt.strftime('%Y-%m-%d %H:%M')} UTC\n\n"
        f"👁 {st.get('viewCount',0)}   👍 {st.get('likeCount',0)}   💬 {st.get('commentCount',0)}\n"
        f"🚨 {fraud}",
        reply_markup=result_kb(vid)
    )


# ================= TAG / TAVSIF =================
@dp.callback_query(F.data.startswith("tags:"))
async def tags(c: CallbackQuery):
    vid = c.data.split(":")[1]
    cur.execute("SELECT tags,description,channel_id FROM videos WHERE video_id=?", (vid,))
    vtags, desc, cid = cur.fetchone()

    data = yt_api("channels", {"part":"brandingSettings","id":cid})
    ctags = data["items"][0]["brandingSettings"]["channel"].get("keywords","")

    await c.message.answer("🏷 VIDEO TAGLAR:\n```\n"+vtags+"\n```", parse_mode="Markdown")
    await c.message.answer("🏷 KANAL TAGLAR:\n```\n"+ctags+"\n```", parse_mode="Markdown")

    for part in split_text(desc):
        await c.message.answer("📝 DESCRIPTION:\n```\n"+part+"\n```", parse_mode="Markdown")

    await c.answer()
# =====================================


@dp.callback_query(F.data.startswith("top:"))
async def top_videos(c: CallbackQuery):
    vid = c.data.split(":")[1]
    cur.execute("SELECT title FROM videos WHERE video_id=?", (vid,))
    title = cur.fetchone()[0]

    data = yt_api("search", {
        "part": "snippet",
        "type": "video",
        "order": "viewCount",
        "maxResults": 10,
        "publishedAfter": (datetime.utcnow()-timedelta(days=30)).isoformat()+"Z",
        "q": title
    })

    text = "🧠 TOP 10 KONKURENT VIDEO:\n\n"
    for i,it in enumerate(data.get("items",[])[:10],1):
        text += f"{i}. {it['snippet']['title']}\nhttps://youtu.be/{it['id']['videoId']}\n\n"

    await c.message.answer(text)
    await c.answer()


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
    for i,it in enumerate(data.get("items",[])[:5],1):
        text += f"{i}. {it['snippet']['channelTitle']} — https://youtube.com/channel/{it['id']['channelId']}\n"

    await c.message.answer(text)
    await c.answer()


async def main():
    print("🤖 BOT ISHLAYAPTI (MESSAGE LIMIT FIXED)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
