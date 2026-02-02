import os, re, time, sqlite3, asyncio, requests
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YT_API_KEY = os.getenv("YOUTUBE_API_KEY")
TZ = timezone(timedelta(hours=5))

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ================= DB =================
db = sqlite3.connect("data.db", check_same_thread=False)
cur = db.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS cache
(key TEXT PRIMARY KEY, value TEXT, ts INTEGER)""")
db.commit()

CACHE_TTL = 1800
RAM = {}

def cache_get(k):
    if k in RAM and time.time() - RAM[k][1] < CACHE_TTL:
        return RAM[k][0]
    cur.execute("SELECT value, ts FROM cache WHERE key=?", (k,))
    r = cur.fetchone()
    if not r or time.time() - r[1] > CACHE_TTL:
        return None
    RAM[k] = (eval(r[0]), r[1])
    return RAM[k][0]

def cache_set(k, v):
    RAM[k] = (v, time.time())
    cur.execute("REPLACE INTO cache VALUES (?,?,?)",
                (k, repr(v), int(time.time())))
    db.commit()

# ================= HELPERS =================
def vid_from_url(u):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)"]:
        m = re.search(p, u)
        if m: return m.group(1)
    return None

def yt(endpoint, params):
    params["key"] = YT_API_KEY
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params, timeout=8
    )
    r.raise_for_status()
    return r.json()

def nakrutka(views, likes):
    if views == 0: return "⚪ Maʼlumot yo‘q"
    r = likes / views
    if r > 0.25: return "🔴 Nakrutka ehtimoli yuqori"
    if r > 0.1: return "🟡 Shubhali"
    return "🟢 Normal"

# ================= VIDEO =================
def get_video(vid):
    k = f"v:{vid}"
    if c := cache_get(k): return c

    r = yt("videos", {
        "part": "snippet,statistics",
        "id": vid
    })["items"]
    if not r: return None

    v = r[0]
    sn = v["snippet"]
    st = v["statistics"]

    published = datetime.fromisoformat(
        sn["publishedAt"].replace("Z","+00:00")
    ).astimezone(TZ).strftime("%d.%m.%Y %H:%M (Toshkent)")

    data = {
        "title": sn["title"],
        "channel": sn["channelTitle"],
        "desc": sn.get("description",""),
        "tags": sn.get("tags",[]),
        "thumb": sn["thumbnails"]["high"]["url"],
        "views": int(st.get("viewCount",0)),
        "likes": int(st.get("likeCount",0)),
        "comments": int(st.get("commentCount",0)),
        "published": published
    }
    cache_set(k,data)
    return data

# ================= START =================
@dp.message(CommandStart())
async def start(m: types.Message):
    await m.answer(
        "👋 <b>Salom!</b>\n\n"
        "🔗 YouTube video linkini yuboring.\n\n"
        "🧠 TOP nomlar\n"
        "🏷 TAG / TAVSIF\n"
        "🖥 Raqobatchi kanallar"
    )

# ================= HANDLE =================
@dp.message()
async def handle(m: types.Message):
    vid = vid_from_url(m.text or "")
    if not vid: return

    await m.answer("⏳ Video analiz qilinmoqda...")

    data = await asyncio.to_thread(get_video, vid)
    if not data:
        await m.answer("❌ Video topilmadi yoki API cheklangan.")
        return

    like_state = nakrutka(data["views"], data["likes"])

    text = (
        f"<b>{data['title']}</b>\n\n"
        f"🕒 Yuklangan: {data['published']}\n"
        f"📺 Kanal: {data['channel']}\n\n"
        f"📊 <b>Video statistikasi</b>\n"
        f"👁 View: {data['views']}\n"
        f"👍 Like: {data['likes']}\n"
        f"💬 Comment: {data['comments']}\n\n"
        f"⚠️ Likelar soni {like_state}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton("🧠 TOP NOMLAR", callback_data=f"title:{vid}"),
            InlineKeyboardButton("🏷 TAG / TAVSIF", callback_data=f"tags:{vid}")
        ],
        [
            InlineKeyboardButton("🖥 Raqobatchi kanallar", callback_data=f"comp:{vid}")
        ]
    ])

    await m.answer_photo(data["thumb"], caption=text, reply_markup=kb)

# ================= TOP NOMLAR (SEARCH) =================
@dp.callback_query(lambda c: c.data.startswith("title:"))
async def top_titles(c: types.CallbackQuery):
    vid = c.data.split(":")[1]
    data = cache_get(f"v:{vid}")
    base = data["title"].split("|")[0]

    res = yt("search", {
        "part": "snippet",
        "q": base,
        "type": "video",
        "order": "viewCount",
        "maxResults": 25
    })["items"]

    used, out = set(), []
    for i in res:
        t = i["snippet"]["title"]
        if t.lower() in used: continue
        used.add(t.lower())
        out.append(t)
        if len(out) == 10: break

    if not out:
        await c.message.answer("⚠️ O‘xshash nomlar topilmadi.")
        return

    txt = "<b>🧠 TOP NOMLAR (konkurent asosida):</b>\n\n"
    for i,t in enumerate(out,1):
        txt += f"{i}. {t}\n"

    await c.message.answer(txt)

# ================= TAG / TAVSIF =================
@dp.callback_query(lambda c: c.data.startswith("tags:"))
async def tags_cb(c: types.CallbackQuery):
    vid = c.data.split(":")[1]
    data = cache_get(f"v:{vid}")

    # Kanal taglari — search orqali
    q = data["channel"]
    s = yt("search", {
        "part":"snippet",
        "q": q,
        "type":"video",
        "maxResults":10
    })["items"]

    channel_tags = set()
    for i in s:
        channel_tags.update(
            re.findall(r"\w+", i["snippet"]["title"].lower())
        )

    txt = (
        "<b>📺 Kanal taglari:</b>\n<code>"
        + ", ".join(list(channel_tags)[:30]) +
        "</code>\n\n"
        "<b>🏷 Video taglari:</b>\n<code>"
        + ", ".join(data["tags"][:40]) +
        "</code>\n\n"
        "<b>📝 Video description:</b>\n<code>"
        + data["desc"][:3000] +
        "</code>"
    )

    await c.message.answer(txt)

# ================= COMP =================
@dp.callback_query(lambda c: c.data.startswith("comp:"))
async def comp(c: types.CallbackQuery):
    vid = c.data.split(":")[1]
    data = cache_get(f"v:{vid}")
    q = data["title"].split("|")[0]

    res = yt("search", {
        "part":"snippet",
        "q": q,
        "type":"video",
        "order":"viewCount",
        "maxResults":20
    })["items"]

    ch = {}
    for i in res:
        name = i["snippet"]["channelTitle"]
        ch[name] = ch.get(name,0)+1

    txt = "<b>🖥 RAQOBATCHI KANALLAR (TOP):</b>\n\n"
    for i,(k,v) in enumerate(sorted(ch.items(), key=lambda x:-x[1])[:10],1):
        txt += f"{i}. {k} — {v} video\n"

    await c.message.answer(txt)

# ================= RUN =================
async def main():
    print("🤖 BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
