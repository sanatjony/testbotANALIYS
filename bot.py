import os, re, sqlite3, asyncio, time, json
from datetime import datetime, timedelta, timezone
import requests

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEYS = [k.strip() for k in os.getenv("YOUTUBE_API_KEYS","").split(",") if k.strip()]
ADMIN_ID = int(os.getenv("ADMIN_ID","0"))

DAILY_CREDITS = 5
TZ_TASHKENT = timezone(timedelta(hours=5))

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ================= DB =================
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    data TEXT,
    ts INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    credits INTEGER,
    reset_ts INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS requests (
    user_id INTEGER,
    link TEXT,
    ts INTEGER,
    UNIQUE(user_id, link)
)
""")

db.commit()

RAM = {}
CACHE_TTL = 3600

# ================= CACHE =================
def cache_get(key):
    if key in RAM:
        return RAM[key]
    cur.execute("SELECT data, ts FROM cache WHERE key=?", (key,))
    r = cur.fetchone()
    if not r or time.time() - r[1] > CACHE_TTL:
        return None
    data = json.loads(r[0])
    RAM[key] = data
    return data

def cache_set(key, data):
    RAM[key] = data
    cur.execute(
        "REPLACE INTO cache VALUES (?,?,?)",
        (key, json.dumps(data), int(time.time()))
    )
    db.commit()

# ================= CREDIT =================
def next_reset_ts():
    now = datetime.now(TZ_TASHKENT)
    reset = now.replace(hour=18, minute=0, second=0, microsecond=0)
    if now >= reset:
        reset += timedelta(days=1)
    return int(reset.timestamp())

def get_user_credits(user):
    if user.id == ADMIN_ID:
        return None

    cur.execute("SELECT credits, reset_ts FROM users WHERE user_id=?", (user.id,))
    row = cur.fetchone()

    if not row:
        cur.execute(
            "INSERT INTO users VALUES (?,?,?,?)",
            (user.id, user.username, DAILY_CREDITS, next_reset_ts())
        )
        db.commit()
        return DAILY_CREDITS

    credits, reset_ts = row
    if time.time() >= reset_ts:
        credits = DAILY_CREDITS
        reset_ts = next_reset_ts()
        cur.execute(
            "UPDATE users SET credits=?, reset_ts=? WHERE user_id=?",
            (credits, reset_ts, user.id)
        )
        db.commit()

    return credits

def link_used_before(user_id, link):
    cur.execute(
        "SELECT 1 FROM requests WHERE user_id=? AND link=?",
        (user_id, link)
    )
    return cur.fetchone() is not None

def use_credit_if_new(user, link):
    if user.id == ADMIN_ID:
        return True, None

    if link_used_before(user.id, link):
        return True, get_user_credits(user)

    credits = get_user_credits(user)
    if credits <= 0:
        return False, 0

    cur.execute(
        "UPDATE users SET credits=credits-1 WHERE user_id=?",
        (user.id,)
    )
    cur.execute(
        "INSERT OR IGNORE INTO requests VALUES (?,?,?)",
        (user.id, link, int(time.time()))
    )
    db.commit()
    return True, credits - 1

# ================= YT =================
def yt(endpoint, params):
    for k in API_KEYS:
        try:
            params["key"] = k
            r = requests.get(
                f"https://www.googleapis.com/youtube/v3/{endpoint}",
                params=params,
                timeout=10
            )
            if r.status_code == 200:
                return r.json()
        except:
            pass
    raise Exception("YouTube API error")

def extract_video_id(url):
    m = re.search(r"(v=|be/)([\w\-]{11})", url)
    return m.group(2) if m else None

def tashkent_time(iso):
    dt = datetime.fromisoformat(iso.replace("Z","+00:00"))
    return dt.astimezone(TZ_TASHKENT).strftime("%d.%m.%Y %H:%M")

def like_nakrutka(views, likes):
    if views == 0:
        return "⚪ Maʼlumot yetarli emas"
    r = likes / views
    if r > 0.3:
        return "🔴 Nakrutka ehtimoli yuqori"
    if r > 0.15:
        return "🟡 Shubhali"
    return "🟢 Normal"

# ================= BOT =================
@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("🎬 YouTube video linkini yuboring")

@dp.message(F.text)
async def handle(m: Message):
    vid = extract_video_id(m.text)
    if not vid:
        return

    ok, credits_left = use_credit_if_new(m.from_user, m.text)
    if not ok:
        await m.answer("❌ Bugungi kredit tugadi. Ertaga qayta urinib ko‘ring.")
        return

    msg = await m.answer("⏳ Analiz qilinmoqda...")

    js = yt("videos", {"part":"snippet,statistics","id":vid})
    it = js["items"][0]

    nak = like_nakrutka(
        int(it["statistics"].get("viewCount",0)),
        int(it["statistics"].get("likeCount",0))
    )

    credit_line = ""
    if m.from_user.id != ADMIN_ID:
        credit_line = f"\n🎟 Kredit: {credits_left}/{DAILY_CREDITS} (har 24 soatda yangilanadi)"

    text = (
        f"🎬 <b>{it['snippet']['title']}</b>\n\n"
        f"🕒 Yuklangan: {tashkent_time(it['snippet']['publishedAt'])} (Toshkent vaqti)\n"
        f"📺 Kanal: {it['snippet']['channelTitle']}\n\n"
        f"👁 {it['statistics'].get('viewCount','0')}   "
        f"👍 {it['statistics'].get('likeCount','0')}   "
        f"💬 {it['statistics'].get('commentCount','0')}\n"
        f"⚠️ Likelar soni {nak}"
        f"{credit_line}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 TOP KONKURENT NOMLAR", callback_data=f"title:{vid}")],
        [InlineKeyboardButton(text="🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")],
        [InlineKeyboardButton(text="📺 RAQOBATCHI KANALLAR", callback_data=f"comp:{vid}")]
    ])

    await msg.edit_text(text, reply_markup=kb)

# ================= RUN =================
async def main():
    print("🤖 BOT ISHGA TUSHDI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
