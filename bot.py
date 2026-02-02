import asyncio
import re
import os
import time
import sqlite3
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
    raise RuntimeError("ENV xato: BOT_TOKEN yoki YOUTUBE_API_KEYS yo‘q")

BOT_TOKEN = BOT_TOKEN.strip()
YOUTUBE_API_KEY = YOUTUBE_API_KEY.strip()
ADMIN_IDS = {int(x) for x in ADMIN_IDS.split(",") if x.strip().isdigit()}
# =====================================


# ================= CONFIG ==============
CREDIT_DAILY = 5
CACHE_TTL = 6 * 3600
# =====================================


# ================= DB ==================
conn = sqlite3.connect("bot.db")
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    credit INTEGER,
    last_reset INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS videos(
    video_id TEXT PRIMARY KEY,
    title TEXT,
    channel TEXT,
    channel_id TEXT,
    category_en TEXT,
    published TEXT,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    tags TEXT,
    description TEXT,
    updated_at INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS submissions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    video_id TEXT,
    video_url TEXT,
    created_at INTEGER
)""")

conn.commit()
# =====================================


# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()

YOUTUBE_REGEX = r"(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+)"


# ================= HELPERS =============
def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

def extract_video_id(url: str):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def detect_link_type(url: str):
    if re.search(r"(watch\?v=|youtu\.be/|/shorts/)", url):
        return "video"
    if re.search(r"/channel/|/c/|/user/|/@", url):
        return "channel"
    return "unknown"

def yt_api(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=20
    )
    r.raise_for_status()
    return r.json()

# ===== CATEGORY MAP (3 TIL) ============
CATEGORY_MAP = {
    "Gaming": ("O‘yinlar", "Игры"),
    "Entertainment": ("Ko‘ngilochar", "Развлечения"),
    "Music": ("Musiqa", "Музыка"),
    "Education": ("Ta’lim", "Образование"),
    "News & Politics": ("Yangiliklar va siyosat", "Новости и политика"),
}

def map_category(en_name):
    uz, ru = CATEGORY_MAP.get(en_name, ("Noma’lum", "Неизвестно"))
    return uz, ru, en_name

# ===== CREDIT =========================
def get_credit(uid):
    if is_admin(uid):
        return 999999

    now = int(time.time())
    cur.execute("SELECT credit,last_reset FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if not row:
        cur.execute("INSERT INTO users VALUES (?,?,?)", (uid, CREDIT_DAILY, now))
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
    if not is_admin(uid):
        cur.execute(
            "UPDATE users SET credit=credit-1 WHERE user_id=? AND credit>0",
            (uid,)
        )
        conn.commit()

# ===== NAKRUTKA =======================
def detect_activity(views, likes, comments, hours):
    if views <= 0:
        return "⚪ Ma’lumot yetarli emas"

    like_ratio = likes / views
    comment_ratio = comments / views if views else 0

    if likes > views:
        return "🔴 LIKE NAKRUTKA"
    if like_ratio >= 0.30:
        return "🔴 LIKE NAKRUTKA"
    if like_ratio >= 0.20 and comment_ratio < 0.002:
        return "🟠 SHUBHALI FAOLLIGI"
    if hours < 3 and views > 5000 and like_ratio > 0.15:
        return "🟠 TEZ SUN’IY O‘SISH"

    return "🟢 NORMAL FAOLLIGI"

# ===== INLINE KB ======================
def result_kb(vid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🧠 TOP 10 KONKURENT VIDEO", callback_data=f"top:{vid}")],
        [InlineKeyboardButton("📺 RAQOBATCHI KANALLAR", callback_data=f"channels:{vid}")],
        [InlineKeyboardButton("🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")]
    ])

# ================= START ===============
@dp.message(Command("start"))
async def start(m: Message):
    name = m.from_user.first_name or "do‘st"
    credit = "∞ (ADMIN)" if is_admin(m.from_user.id) else f"{get_credit(m.from_user.id)}/{CREDIT_DAILY} (24 soatda yangilanadi)"

    await m.answer(
        f"Assalom aleykum, {name} 👋\n\n"
        f"📊 YouTube ANALIZ BOTI\n\n"
        f"💳 Kredit: {credit}\n\n"
        f"👉 YouTube video linkni yuboring va tezkor analiz qilamiz!!!"
    )

# ================= EXPORT ==============
@dp.message(Command("export"))
async def export_txt(m: Message):
    if not is_admin(m.from_user.id):
        await m.answer("❌ Faqat admin uchun.")
        return

    cur.execute("SELECT user_id,username,video_url,video_id,created_at FROM submissions ORDER BY created_at DESC")
    rows = cur.fetchall()
    if not rows:
        await m.answer("ℹ️ Ma’lumot yo‘q.")
        return

    fname = "export.txt"
    with open(fname, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(
                f"📅 {datetime.fromtimestamp(r[4]).strftime('%Y-%m-%d %H:%M')}\n"
                f"👤 @{r[1] or 'no_username'} ({r[0]})\n"
                f"🔗 {r[2]}\n"
                f"🆔 {r[3]}\n"
                "--------------------------\n\n"
            )

    await m.answer_document(FSInputFile(fname))

# ================= ANALYZE =============
@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def analyze(m: Message):
    if detect_link_type(m.text) != "video":
        await m.answer("❌ Iltimos, faqat **video link** yuboring.")
        return

    uid = m.from_user.id
    if get_credit(uid) <= 0:
        await m.answer("❌ Kredit tugagan.")
        return

    use_credit(uid)
    vid = extract_video_id(m.text)

    cur.execute(
        "INSERT INTO submissions(user_id,username,video_id,video_url,created_at) VALUES (?,?,?,?,?)",
        (uid, m.from_user.username, vid, m.text, int(time.time()))
    )
    conn.commit()

    cur.execute("SELECT * FROM videos WHERE video_id=?", (vid,))
    row = cur.fetchone()

    now = int(time.time())
    if not row or now - row[-1] > CACHE_TTL:
        data = yt_api("videos", {"part": "snippet,statistics", "id": vid})
        it = data["items"][0]
        sn, st = it["snippet"], it["statistics"]

        cat_data = yt_api("videoCategories", {
            "part": "snippet",
            "id": sn["categoryId"],
            "regionCode": "US"
        })
        cat_en = cat_data["items"][0]["snippet"]["title"]

        cur.execute("""
            INSERT OR REPLACE INTO videos
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            vid,
            sn["title"],
            sn["channelTitle"],
            sn["channelId"],
            cat_en,
            sn["publishedAt"],
            int(st.get("viewCount", 0)),
            int(st.get("likeCount", 0)),
            int(st.get("commentCount", 0)),
            ", ".join(sn.get("tags", [])),
            sn.get("description", ""),
            now
        ))
        conn.commit()
        cur.execute("SELECT * FROM videos WHERE video_id=?", (vid,))
        row = cur.fetchone()

    _, title, channel, cid, cat_en, published, views, likes, comments, tags, desc, _ = row
    uz_cat, ru_cat, en_cat = map_category(cat_en)

    pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
    hours = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600

    caption = (
        f"🎬 <b>{title}</b>\n\n"
        f"📂 Kategoriya:\n"
        f"🇺🇿 {uz_cat}\n"
        f"🇷🇺 {ru_cat}\n"
        f"🇬🇧 {en_cat}\n\n"
        f"📺 Kanal: {channel}\n"
        f"⏰ Yuklangan: {pub_dt.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"👁 {views}   👍 {likes}   💬 {comments}\n\n"
        f"🚨 {detect_activity(views, likes, comments, hours)}\n\n"
        f"💳 Qolgan kredit: {get_credit(uid)}/{CREDIT_DAILY}"
    )

    await bot.send_photo(
        m.chat.id,
        photo=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        caption=caption,
        parse_mode="HTML",
        reply_markup=result_kb(vid)
    )

# ================= CALLBACKS ===========
@router.callback_query(F.data.startswith("top:"))
async def cb_top(c: CallbackQuery):
    vid = c.data.split(":")[1]
    title = cur.execute("SELECT title FROM videos WHERE video_id=?", (vid,)).fetchone()[0]

    search = yt_api("search", {
        "part": "snippet",
        "type": "video",
        "order": "viewCount",
        "maxResults": 10,
        "q": title,
        "publishedAfter": (datetime.utcnow()-timedelta(days=30)).isoformat()+"Z"
    })

    ids = [i["id"]["videoId"] for i in search["items"]]
    stats = yt_api("videos", {"part": "statistics", "id": ",".join(ids)})
    view_map = {i["id"]: int(i["statistics"].get("viewCount", 0)) for i in stats["items"]}

    text = "🧠 TOP 10 KONKURENT VIDEO:\n\n"
    for i, it in enumerate(search["items"], 1):
        v = it["id"]["videoId"]
        text += f"{i}. {it['snippet']['title']}\n👁 {view_map.get(v,0):,}\nhttps://youtu.be/{v}\n\n"

    await c.message.answer(text)
    await c.answer()

@router.callback_query(F.data.startswith("channels:"))
async def cb_channels(c: CallbackQuery):
    vid = c.data.split(":")[1]
    title = cur.execute("SELECT title FROM videos WHERE video_id=?", (vid,)).fetchone()[0]

    data = yt_api("search", {
        "part": "snippet",
        "type": "channel",
        "maxResults": 5,
        "q": title
    })

    text = "📺 RAQOBATCHI KANALLAR (TOP 5):\n\n"
    for i, it in enumerate(data["items"], 1):
        text += f"{i}. {it['snippet']['channelTitle']} — https://youtube.com/channel/{it['id']['channelId']}\n"

    await c.message.answer(text)
    await c.answer()

@router.callback_query(F.data.startswith("tags:"))
async def cb_tags(c: CallbackQuery):
    vid = c.data.split(":")[1]
    tags, desc, cid = cur.execute(
        "SELECT tags,description,channel_id FROM videos WHERE video_id=?",
        (vid,)
    ).fetchone()

    ch = yt_api("channels", {"part": "brandingSettings", "id": cid})
    ch_tags = ch["items"][0]["brandingSettings"]["channel"].get("keywords", "")

    await c.message.answer(f"🏷 VIDEO TAGLAR:\n```\n{tags}\n```", parse_mode="Markdown")
    await c.message.answer(f"🏷 KANAL TAGLAR:\n```\n{ch_tags}\n```", parse_mode="Markdown")

    for part in [desc[i:i+4000] for i in range(0, len(desc), 4000)]:
        await c.message.answer(f"📝 DESCRIPTION:\n```\n{part}\n```", parse_mode="Markdown")

    await c.answer()

# ================= MAIN ================
async def main():
    dp.include_router(router)
    print("🤖 BOT ISHLAYAPTI — FULL FUNCTIONAL")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
