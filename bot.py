import asyncio
import re
import sqlite3
import time
import os
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

CREDIT_DAILY = 5
TTL_VIDEO = 6 * 3600

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

YOUTUBE_REGEX = r"(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+)"

def is_admin(uid): return uid in ADMIN_IDS

def extract_video_id(url):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def detect_link_type(url):
    if re.search(r"(watch\?v=|youtu\.be/|/shorts/)", url): return "video"
    if re.search(r"/channel/|/c/|/user/|/@", url): return "channel"
    return "unknown"

def yt_api(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(f"https://www.googleapis.com/youtube/v3/{endpoint}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def preload_categories():
    cur.execute("SELECT COUNT(*) FROM categories")
    if cur.fetchone()[0] > 0: return
    data = yt_api("videoCategories", {"part":"snippet","regionCode":"US"})
    for it in data.get("items", []):
        cur.execute("INSERT OR IGNORE INTO categories VALUES (?,?)",(it["id"],it["snippet"]["title"]))
    conn.commit()

def resolve_category(cid):
    cur.execute("SELECT name FROM categories WHERE category_id=?", (cid,))
    r = cur.fetchone()
    return r[0] if r else "Unknown"

def get_credit(uid):
    if is_admin(uid): return 999999
    now = int(time.time())
    cur.execute("SELECT credit,last_reset FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone()
    if not r:
        cur.execute("INSERT INTO users VALUES (?,?,?)",(uid,CREDIT_DAILY,now))
        conn.commit()
        return CREDIT_DAILY
    credit,last = r
    if now-last>=86400:
        credit=CREDIT_DAILY
        cur.execute("UPDATE users SET credit=?,last_reset=? WHERE user_id=?",(credit,now,uid))
        conn.commit()
    return credit

def use_credit(uid):
    if not is_admin(uid):
        cur.execute("UPDATE users SET credit=credit-1 WHERE user_id=? AND credit>0",(uid,))
        conn.commit()

def detect_like_fraud(v,l,c,h):
    if v<=0: return "⚪ Ma’lumot yetarli emas"
    r=l/v
    if l>v: return "🔴 LIKE NAKRUTKA"
    if r>=0.30: return "🔴 LIKE NAKRUTKA"
    if r>=0.20 and c/v<0.002: return "🟠 SHUBHALI FAOLLIGI"
    if h<3 and v>5000 and r>0.15: return "🟠 TEZ O‘SISH"
    return "🟢 NORMAL FAOLLIGI"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()

def result_kb(vid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 TOP 10 KONKURENT VIDEO", callback_data=f"top:{vid}")],
        [InlineKeyboardButton(text="📺 RAQOBATCHI KANALLAR", callback_data=f"channels:{vid}")],
        [InlineKeyboardButton(text="🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")]
    ])

@dp.message(Command("start"))
async def start(m: Message):
    preload_categories()
    name = m.from_user.first_name or "do‘st"
    credit = "∞ (ADMIN)" if is_admin(m.from_user.id) else f"{get_credit(m.from_user.id)}/{CREDIT_DAILY} (24 soatda yangilanadi)"
    await m.answer(
        f"Assalom aleykum, {name} 👋\n\n"
        f"📊 YouTube ANALIZ BOTI\n\n"
        f"💳 Kredit: {credit}\n\n"
        f"👉 YouTube linkni yuboring va tezkor analiz qilamiz!!!"
    )

@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def analyze(m: Message):
    if detect_link_type(m.text)!="video":
        await m.answer("❌ Iltimos, faqat **video link** yuboring.")
        return

    uid=m.from_user.id
    if get_credit(uid)<=0:
        await m.answer("❌ Kredit tugagan.")
        return

    vid=extract_video_id(m.text)
    use_credit(uid)

    data=yt_api("videos",{"part":"snippet,statistics","id":vid})
    it=data["items"][0]
    sn,st=it["snippet"],it["statistics"]

    # ===== THUMBNAIL PREVIEW =====
    await bot.send_photo(
        chat_id=m.chat.id,
        photo=sn["thumbnails"]["high"]["url"],
        caption=(
            f"🎬 {sn['title']}\n"
            f"📺 {sn['channelTitle']}\n"
            f"👁 {st.get('viewCount',0)} | 👍 {st.get('likeCount',0)} | 💬 {st.get('commentCount',0)}"
        )
    )

    dt=datetime.fromisoformat(sn["publishedAt"].replace("Z","+00:00"))
    hours=(datetime.now(timezone.utc)-dt).total_seconds()/3600

    await m.answer(
        f"🎬 {sn['title']}\n"
        f"📂 Kategoriya: {resolve_category(sn.get('categoryId'))}\n"
        f"📺 Kanal: {sn['channelTitle']}\n"
        f"⏰ Yuklangan: {dt.strftime('%Y-%m-%d %H:%M')} UTC\n\n"
        f"👁 {st.get('viewCount',0)}   👍 {st.get('likeCount',0)}   💬 {st.get('commentCount',0)}\n"
        f"🚨 {detect_like_fraud(int(st.get('viewCount',0)),int(st.get('likeCount',0)),int(st.get('commentCount',0)),hours)}\n\n"
        f"💳 Qolgan kredit: {get_credit(uid)}/{CREDIT_DAILY}",
        reply_markup=result_kb(vid)
    )

async def main():
    dp.include_router(router)
    print("🤖 BOT ISHLAYAPTI — THUMBNAIL TEST MODE")
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
