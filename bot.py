import os
import re
import asyncio
from collections import Counter
import requests

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.enums import ParseMode

BOT_TOKEN = os.getenv("BOT_TOKEN")
YT_KEY = os.getenv("YOUTUBE_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"


# ---------- YOUTUBE HELPERS ----------

def yt(endpoint, params):
    try:
        params["key"] = YT_KEY
        r = requests.get(f"{YOUTUBE_API}/{endpoint}", params=params, timeout=10)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def extract_video_id(url: str):
    m = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
    return m.group(1) if m else None


# ---------- START ----------

@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 Salom!\n\n"
        "YouTube video havolasini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 TOP NOMLAR (konkurent asosida)\n"
        "🏷 TOP TAGLAR\n"
        "📺 Raqobatchi kanallar\n\n"
        "chiqarib beraman."
    )


# ---------- VIDEO HANDLER ----------

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

    if not data or not data.get("items"):
        await msg.answer("❌ Video topilmadi yoki API vaqtincha cheklangan.")
        return

    item = data["items"][0]
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})

    title = snippet.get("title", "—")
    views = stats.get("viewCount", "0")
    likes = stats.get("likeCount", "0")
    comments = stats.get("commentCount", "0")

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
    if not vdata or not vdata.get("items"):
        await cb.message.answer("⚠️ Video maʼlumoti olinmadi.")
        return

    query = vdata["items"][0]["snippet"]["title"]

    search = yt("search", {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "viewCount",
        "maxResults": 25
    })

    if not search or not search.get("items"):
        await cb.message.answer("⚠️ O‘xshash videolar topilmadi.")
        return

    results = []
    seen = set()

    for it in search["items"]:
        vid_id = it["id"].get("videoId")
        if not vid_id:
            continue

        t = it["snippet"]["title"]
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)

        stats = yt("videos", {
            "part": "statistics",
            "id": vid_id
        })
        if not stats or not stats.get("items"):
            continue

        views = int(stats["items"][0]["statistics"].get("viewCount", 0))
        results.append((t, views))

        if len(results) == 10:
            break

    if not results:
        await cb.message.answer("⚠️ Yetarli o‘xshash nomlar topilmadi.")
        return

    text = "🧠 <b>OXIRGI 60–90 KUN — KONKURENT TOP NOMLAR:</b>\n\n"
    for i, (t, v) in enumerate(results, 1):
        text += f"{i}. {t}\n👁 {v:,}\n\n"

    await cb.message.answer(text, parse_mode=ParseMode.HTML)


# ---------- TOP TAGS ----------

@dp.callback_query(F.data.startswith("tags:"))
async def top_tags(cb):
    vid = cb.data.split(":")[1]
    await cb.message.answer("⏳ TOP taglar tayyorlanmoqda...")

    vdata = yt("videos", {"part": "snippet", "id": vid})
    if not vdata or not vdata.get("items"):
        await cb.message.answer("⚠️ Video maʼlumoti olinmadi.")
        return

    snippet = vdata["items"][0]["snippet"]
    title = snippet.get("title", "")
    desc = snippet.get("description", "")

    words = re.findall(r"[a-zA-Z]{4,}", (title + " " + desc).lower())
    counter = Counter(words)

    search = yt("search", {
        "part": "snippet",
        "q": title,
        "type": "video",
        "maxResults": 10
    })

    if search and search.get("items"):
        for it in search["items"]:
            d = it["snippet"].get("description", "")
            for w in re.findall(r"[a-zA-Z]{4,}", d.lower()):
                counter[w] += 1

    tags = [w for w, _ in counter.most_common(25)]
    if not tags:
        await cb.message.answer("⚠️ Taglar topilmadi.")
        return

    await cb.message.answer(
        "🏷 <b>TOP TAGLAR (copy-paste):</b>\n\n" + ", ".join(tags),
        parse_mode=ParseMode.HTML
    )


# ---------- COMPETITOR CHANNELS ----------

@dp.callback_query(F.data.startswith("channels:"))
async def channels(cb):
    vid = cb.data.split(":")[1]
    await cb.message.answer("⏳ Raqobatchi kanallar analiz qilinmoqda...")

    vdata = yt("videos", {"part": "snippet", "id": vid})
    if not vdata or not vdata.get("items"):
        await cb.message.answer("⚠️ Video maʼlumoti olinmadi.")
        return

    query = vdata["items"][0]["snippet"]["title"]

    search = yt("search", {
        "part": "snippet",
        "q": query,
        "type": "channel",
        "maxResults": 10
    })

    if not search or not search.get("items"):
        await cb.message.answer("⚠️ Kanallar topilmadi.")
        return

    text = "📺 <b>RAQOBATCHI KANALLAR:</b>\n\n"
    for i, it in enumerate(search["items"], 1):
        text += f"{i}. {it['snippet']['channelTitle']}\n"

    await cb.message.answer(text, parse_mode=ParseMode.HTML)


# ---------- RUN ----------

async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
