import asyncio
import re
import sqlite3
import time
import os
import csv
import requests
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile
)
from aiogram.filters import Command

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEYS")
ADMIN_IDS = os.getenv("ADMIN_IDS", "")

if not BOT_TOKEN or not YOUTUBE_API_KEY:
    raise RuntimeError("BOT_TOKEN yoki YOUTUBE_API_KEYS yo‘q")

BOT_TOKEN = BOT_TOKEN.strip()
YOUTUBE_API_KEY = YOUTUBE_API_KEY.strip()
ADMIN_IDS = {int(x) for x in ADMIN_IDS.split(",") if x.strip().isdigit()}
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

cur.execute("""CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    video_id TEXT,
    video_url TEXT,
    created_at INTEGER
)""")

conn.commit()
# =====================================


# ================= HELPERS =============
YOUTUBE_REGEX = r"(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+)"

def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

def extract_video_id(url: str):
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
    data = yt_api("videoCategories", {
        "part": "snippet",
        "regionCode": "US"
    })
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


# ================= CREDIT ==============
def get_credit(uid):
    if is_admin(uid):
        return 999999

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
    if is_admin(uid):
        return
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
    if hours < 3 and views > 5000 and like_ratio > 0.15:
        return "🟠 TEZ SUN’IY O‘SISH"
    return "🟢 NORMAL FAOLLIGI"
# =====================================


# ================= BOT SETUP ===========
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()
# =====================================


def result_kb(vid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 TOP 10 KONKURENT VIDEO", callback_data=f"top:{vid}")],
        [InlineKeyboardButton(text="📺 RAQOBATCHI KANALLAR", callback_data=f"channels:{vid}")],
        [InlineKeyboardButton(text="🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")]
    ])


# ================= COMMANDS ============
@dp.message(Command("start"))
async def start(m: Message):
    preload_categories()
    credit = get_credit(m.from_user.id)
    admin_flag = " (ADMIN)" if is_admin(m.from_user.id) else ""
    await m.answer(
        "👋 YouTube ANALIZ BOT\n\n"
        f"💳 Kredit: {credit}/{CREDIT_DAILY}{admin_flag}\n"
        "👉 YouTube linkni yuboring"
    )


@dp.message(Command("export"))
async def export_data(m: Message):
    if not is_admin(m.from_user.id):
        await m.answer("❌ Bu buyruq faqat admin uchun.")
        return

    cur.execute("""
        SELECT user_id, username, video_url, video_id, created_at
        FROM submissions
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()

    if not rows:
        await m.answer("ℹ️ Hozircha hech qanday link yo‘q.")
        return

    filename = "submissions_export.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "user_id", "username", "video_url", "video_id", "created_at"
        ])
        for r in rows:
            writer.writerow([
                r[0],
                r[1] or "",
                r[2],
                r[3],
                datetime.fromtimestamp(r[4]).strftime("%Y-%m-%d %H:%M:%S")
            ])

    await m.answer_document(FSInputFile(filename))
# =====================================


# ================= ANALYZE ============
@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def analyze(m: Message):
    uid = m.from_user.id
    credit = get_credit(uid)

    if credit <= 0:
        await m.answer("❌ Kredit tugagan. 24 soatda yangilanadi.")
        return

    use_credit(uid)

    vid = extract_video_id(m.text)
    if not vid:
        return

    cur.execute("""
        INSERT INTO submissions (user_id, username, video_id, video_url, created_at)
        VALUES (?,?,?,?,?)
    """, (
        uid,
        m.from_user.username,
        vid,
        m.text,
        int(time.time())
    ))
    conn.commit()

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
        row = cur.execute("SELECT * FROM videos WHERE video_id=?", (vid,)).fetchone()

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


# ================= CALLBACKS ===========
@router.callback_query(F.data.startswith("top:"))
async def top_videos(c: CallbackQuery):
    vid = c.data.split(":")[1]
    title = cur.execute(
        "SELECT title FROM videos WHERE video_id=?",
        (vid,)
    ).fetchone()[0]

    # 1️⃣ search.list
    search_data = yt_api("search", {
        "part": "snippet",
        "type": "video",
        "order": "viewCount",
        "maxResults": 10,
        "publishedAfter": (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z",
        "q": title
    })

    video_ids = [it["id"]["videoId"] for it in search_data.get("items", [])[:10]]

    # 2️⃣ videos.list (statistics)
    stats_data = yt_api("videos", {
        "part": "statistics",
        "id": ",".join(video_ids)
    })

    views_map = {
        it["id"]: int(it["statistics"].get("viewCount", 0))
        for it in stats_data.get("items", [])
    }

    text = "🧠 TOP 10 KONKURENT VIDEO:\n\n"
    for i, it in enumerate(search_data.get("items", [])[:10], 1):
        v_id = it["id"]["videoId"]
        title_v = it["snippet"]["title"]
        views_v = views_map.get(v_id, 0)
        text += (
            f"{i}. {title_v}\n"
            f"👁 {views_v:,}\n"
            f"https://youtu.be/{v_id}\n\n"
        )

    await c.message.answer(text)
    await c.answer()


@router.callback_query(F.data.startswith("channels:"))
async def channels(c: CallbackQuery):
    vid = c.data.split(":")[1]
    title = cur.execute(
        "SELECT title FROM videos WHERE video_id=?",
        (vid,)
    ).fetchone()[0]

    data = yt_api("search", {
        "part": "snippet",
        "type": "channel",
        "maxResults": 5,
        "q": title
    })

    text = "📺 RAQOBATCHI KANALLAR (TOP 5):\n\n"
    for i, it in enumerate(data.get("items", [])[:5], 1):
        text += f"{i}. {it['snippet']['channelTitle']} — https://youtube.com/channel/{it['id']['channelId']}\n"

    await c.message.answer(text)
    await c.answer()


@router.callback_query(F.data.startswith("tags:"))
async def tags(c: CallbackQuery):
    vid = c.data.split(":")[1]
    vtags, desc, cid = cur.execute(
        "SELECT tags, description, channel_id FROM videos WHERE video_id=?",
        (vid,)
    ).fetchone()

    data = yt_api("channels", {
        "part": "brandingSettings",
        "id": cid
    })
    ctags = data["items"][0]["brandingSettings"]["channel"].get("keywords", "")

    await c.message.answer("🏷 VIDEO TAGLAR:\n```\n"+vtags+"\n```", parse_mode="Markdown")
    await c.message.answer("🏷 KANAL TAGLAR:\n```\n"+ctags+"\n```", parse_mode="Markdown")

    for part in split_text(desc):
        await c.message.answer("📝 DESCRIPTION:\n```\n"+part+"\n```", parse_mode="Markdown")

    await c.answer()
# =====================================


# ================= MAIN ================
async def main():
    dp.include_router(router)
    print("🤖 BOT ISHLAYAPTI — TOP 10 VIEWCOUNT QO‘SHILDI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
