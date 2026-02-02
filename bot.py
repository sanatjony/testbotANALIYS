import os
import re
import asyncio
from collections import Counter
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.enums import ParseMode
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
YT_KEY = os.getenv("YOUTUBE_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"

# ---------- UTILS ----------

def extract_video_id(url: str):
    m = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
    return m.group(1) if m else None

def yt(endpoint, params):
    params["key"] = YT_KEY
    r = requests.get(f"{YOUTUBE_API}/{endpoint}", params=params, timeout=10)
    if r.status_code != 200:
        return None
    return r.json()

# ---------- START ----------

@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 Salom!\n\n"
        "YouTube video havolasini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 TOP NOMLAR (konkurent asosida)\n"
        "🏷 TOP TAGLAR\n"
        "📺 Raqobatchi kanallar\n"
        "chiqarib beraman."
    )

# ---------- VIDEO HANDLE ----------

@dp.message(F.text.contains("youtube"))
async def handle_video(msg: Message):
    vid = extract_video_id(msg.text)
    if not vid:
        await msg.answer("❌ Video ID topilmadi.")
        return

    data = yt("videos", {
        "part": "snippet,statistics",
        "id": vid
    })

    if not data or not data["items"]:
        await msg.answer("❌ Video topilmadi yoki API cheklangan.")
        return

    v = data["items"][0]
    title = v["snippet"]["title"]
    views = v["statistics"].get("viewCount", "0")
    likes = v["statistics"].get("likeCount", "0")
    comments = v["statistics"].get("commentCount", "0")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧠 TOP NOMLAR", callback_data=f"titles:{vid}"),
            InlineKeyboardButton(text="🏷 TOP TAGLAR", callback_data=f"tags:{vid}")
        ],
        [
            InlineKeyboardButton(text="📺 Raqobatchi kanallar", callback_data=f"channels:{vid}")
        ]
    ])

    await msg.answer(
        f"🎬 <b>{title}</b>\n\n"
        f"👁 {views}   👍 {likes}   💬 {comments}\n\n"
        f"👇 Funksiyani tanlang:",
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )

# ---------- TOP TITLES ----------

@dp.callback_query(F.data.startswith("titles:"))
async def top_titles(cb):
    vid = cb.data.split(":")[1]
    await cb.message.answer("⏳ TOP nomlar analiz qilinmoqda...")

    vdata = yt("videos", {"part": "snippet", "id": vid})
    q = vdata["items"][0]["snippet"]["title"]

    search = yt("search", {
        "part": "snippet",
        "q": q,
        "type": "video",
        "order": "viewCount",
        "maxResults": 25
    })

    titles = []
    seen = set()

    for it in search["items"]:
        t = it["snippet"]["title"]
        if t.lower() in seen:
            continue
        seen.add(t.lower())

        stats = yt("videos", {
            "part": "statistics",
            "id": it["id"]["videoId"]
        })
        if not stats or not stats["items"]:
            continue

        v = int(stats["items"][0]["statistics"].get("viewCount", 0))
        titles.append((t, v))
        if len(titles) == 10:
            break

    if not titles:
        await cb.message.answer("⚠️ Yetarli o‘xshash nomlar topilmadi.")
        return

    text = "🧠 <b>OXIRGI 60–90 KUN — KONKURENT TOP NOMLAR:</b>\n\n"
    for i, (t, v) in enumerate(titles, 1):
        text += f"{i}. {t}\n👁 {v:,}\n\n"

    await cb.message.answer(text, parse_mode=ParseMode.HTML)

# ---------- TOP TAGS ----------

@dp.callback_query(F.data.startswith("tags:"))
async def top_tags(cb):
    vid = cb.data.split(":")[1]
    await cb.message.answer("⏳ TOP taglar tayyorlanmoqda...")

    vdata = yt("videos", {"part": "snippet", "id": vid})
    title = vdata["items"][0]["snippet"]["title"]
    desc = vdata["items"][0]["snippet"].get("description", "")

    words = re.findall(r"[a-zA-Z]{4,}", (title + " " + desc).lower())
    base = Counter(words)

    search = yt("search", {
        "part": "snippet",
        "q": title,
        "type": "video",
        "maxResults": 10
    })

    for it in search["items"]:
        d = it["snippet"].get("description", "")
        for w in re.findall(r"[a-zA-Z]{4,}", d.lower()):
            base[w] += 1

    tags = [w for w, _ in base.most_common(25)]
    if not tags:
        tags = words[:15]

    await cb.message.answer(
        "🏷 <b>TOP TAGLAR (copy-paste):</b>\n\n"
        + ", ".join(tags),
        parse_mode=ParseMode.HTML
    )

# ---------- COMPETITOR CHANNELS ----------

@dp.callback_query(F.data.startswith("channels:"))
async def channels(cb):
    vid = cb.data.split(":")[1]
    await cb.message.answer("⏳ Raqobatchi kanallar analiz qilinmoqda...")

    vdata = yt("videos", {"part": "snippet", "id": vid})
    q = vdata["items"][0]["snippet"]["title"]

    search = yt("search", {
        "part": "snippet",
        "q": q,
        "type": "channel",
        "maxResults": 10
    })

    res = "📺 <b>RAQOBATCHI KANALLAR:</b>\n\n"
    for i, it in enumerate(search["items"], 1):
        res += f"{i}. {it['snippet']['channelTitle']}\n"

    await cb.message.answer(res, parse_mode=ParseMode.HTML)

# ---------- RUN ----------

async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
