import os, re, sqlite3, asyncio, time, json
from datetime import datetime, timedelta, timezone
import requests

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEYS = [k.strip() for k in os.getenv("YOUTUBE_API_KEYS","").split(",") if k.strip()]
ADMIN_ID = int(os.getenv("ADMIN_ID","0"))

TZ_TASHKENT = timezone(timedelta(hours=5))
DAILY_CREDITS = 5

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
    username TEXT,
    link TEXT,
    ts INTEGER
)
""")

db.commit()

RAM = {}
CACHE_TTL = 3600

# ================= HELPERS =================
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

def next_reset_ts():
    # Google API reset ≈ 00:00 PT → ~18:00 Toshkent
    now = datetime.now(TZ_TASHKENT)
    reset = now.replace(hour=18, minute=0, second=0, microsecond=0)
    if now >= reset:
        reset += timedelta(days=1)
    return int(reset.timestamp())

def get_user(user):
    if user.id == ADMIN_ID:
        return None  # admin cheklanmaydi

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

def use_credit(user):
    if user.id == ADMIN_ID:
        return True

    credits = get_user(user)
    if credits <= 0:
        return False

    cur.execute(
        "UPDATE users SET credits=credits-1 WHERE user_id=?",
        (user.id,)
    )
    db.commit()
    return True

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

# ================= BOT =================
@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("🎬 YouTube video linkini yuboring")

@dp.message(F.text)
async def handle(m: Message):
    vid = extract_video_id(m.text)
    if not vid:
        return

    if not use_credit(m.from_user):
        await m.answer("❌ Bugungi kredit tugadi. Ertaga qayta urinib ko‘ring.")
        return

    cur.execute(
        "INSERT INTO requests VALUES (?,?,?,?)",
        (m.from_user.id, m.from_user.username, m.text, int(time.time()))
    )
    db.commit()

    credits_left = get_user(m.from_user)

    msg = await m.answer("⏳ Analiz qilinmoqda...")

    js = yt("videos", {"part":"snippet,statistics","id":vid})
    it = js["items"][0]

    text = (
        f"🎬 <b>{it['snippet']['title']}</b>\n\n"
        f"📺 Kanal: {it['snippet']['channelTitle']}\n"
        f"👁 {it['statistics'].get('viewCount','0')}   "
        f"👍 {it['statistics'].get('likeCount','0')}   "
        f"💬 {it['statistics'].get('commentCount','0')}\n\n"
        f"🎟 Kredit: {credits_left}/{DAILY_CREDITS}"
    )

    await msg.edit_text(text)

# ================= ADMIN EXPORT =================
@dp.message(F.text == "/export")
async def export(m: Message):
    if m.from_user.id != ADMIN_ID:
        return

    cur.execute("SELECT * FROM requests")
    rows = cur.fetchall()

    txt = ""
    for r in rows:
        txt += f"{r[0]} | @{r[1]} | {r[2]} | {datetime.fromtimestamp(r[3])}\n"

    with open("export.txt","w",encoding="utf-8") as f:
        f.write(txt)

    await m.answer_document(open("export.txt","rb"))

# ================= RUN =================
async def main():
    print("🤖 BOT ISHGA TUSHDI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
