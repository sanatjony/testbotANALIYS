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

cur.execute("""CREATE TABLE IF NOT EXISTS categories (
    category_id TEXT PRIMARY KEY,
    name TEXT
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
    cur.execute("SELECT name FROM categories WHERE category_id=?", (cat_id,))
    row = cur.fetchone()
    return row[0] if row else "Unknown"
# =====================================

# ================= CREDIT (FIXED) ======
def get_credit(uid):
    now = int(time.time())
    cur.execute("SELECT credit, last_reset FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if not row:
        cur.execute(
            "INSERT INTO users VALUES (?,?,?)",
            (uid, CREDIT_DAILY, now)
        )
        conn.commit()
        return CREDIT_DAILY

    credit, last = row
    if now - last >= 86400:
        credit = CREDIT_DAILY
        cur.execute(
            "UPDATE users SET credit=?, last_reset=? WHERE user_id=?",
            (credit, now, uid)
        )
        conn.commit()
    return credit

def use_credit(uid):
    cur.execute(
        "UPDATE users SET credit = credit - 1 WHERE user_id=? AND credit > 0",
        (uid,)
    )
    conn.commit()
# =====================================

# ================= NAKRUTKA ===========
def detect_like_fraud(views, likes, comments, hours):
    if views <= 0:
        return "⚪ Ma’lumot yetarli emas"

    like_ratio = likes / views
    comment_ratio = comments / views if views else 0

    if likes > views:
        return "🔴 LIKE NAKRUTKA (LIKELAR VIEWDAN KO‘P)"
    if like_ratio >= 0.30:
        return f"🔴 LIKE NAKRUTKA ({like_ratio*100:.0f}%)"
    if like_ratio >= 0.20 and comment_ratio < 0.002:
        return "🟠 SHUBHALI FAOLLIGI"
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
        "👋 YouTube ANALIZ BOT\n\n"
        f"💳 Kredit: {credit}/{CREDIT_DAILY}\n"
        "👉 YouTube linkni yuboring"
    )

# ================= ANALYZE (KREDIT FIXED) ========
@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def analyze(m: Message):
    uid = m.from_user.id

    credit = get_credit(uid)
    if credit <= 0:
        await m.answer("❌ Kredit tugagan. 24 soatda yangilanadi.")
        return

    # 🔒 MUHIM: HAR ANALIZ = 1 KREDIT
    use_credit(uid)

    vid = extract_video_id(m.text)
    if not vid:
        return

    now_ts = int(time.time())
    cur.execute("SELECT * FROM videos WHERE video_id=?", (vid,))
    row = cur.fetchone()

    if not row or now_ts - row[-1] > TTL_VIDEO:
        data = yt_api("videos", {"part": "snippet,statistics", "id": vid})
        it = data["items"][0]
        sn, st = it["snippet"], it["statistics"]

        category = resolve_category(sn.get("categoryId"))

        cur.execute("""
            INSERT OR REPLACE INTO videos
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            vid,
            sn["title"],
            sn["channelTitle"],
            sn["channelId"],
            category,
            sn["publishedAt"],
            int(st.get("viewCount", 0)),
            int(st.get("likeCount", 0)),
            int(st.get("commentCount", 0)),
            ", ".join(sn.get("tags", [])),
            sn.get("description", ""),
            now_ts
        ))
        conn.commit()

        row = (
            vid,
            sn["title"],
            sn["channelTitle"],
            sn["channelId"],
            category,
            sn["publishedAt"],
            int(st.get("viewCount", 0)),
            int(st.get("likeCount", 0)),
            int(st.get("commentCount", 0)),
            ", ".join(sn.get("tags", [])),
            sn.get("description", ""),
            now_ts
        )

    _, title, channel, cid, category, published, views, likes, comments, tags, desc, _ = row

    dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
    hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    fraud = detect_like_fraud(views, likes, comments, hours)

    credit_left = get_credit(uid)

    await m.answer(
        f"🎬 {title}\n"
        f"📂 Kategoriya: {category}\n"
        f"📺 Kanal: {channel}\n"
        f"⏰ Yuklangan: {dt.strftime('%Y-%m-%d %H:%M')} UTC\n\n"
        f"👁 {views}   👍 {likes}   💬 {comments}\n"
        f"🚨 {fraud}\n\n"
        f"💳 Qolgan kredit: {credit_left}/{CREDIT_DAILY}",
        reply_markup=result_kb(vid)
    )
# =====================================

async def main():
    print("🤖 BOT ISHLAYAPTI (KREDIT FIXED)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
