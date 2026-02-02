import os
import re
import asyncio
import requests
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart

BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"

# ---------- HELPERS ----------

def extract_video_id(url: str):
    patterns = [
        r"v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})"
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def yt(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(f"{YOUTUBE_API}/{endpoint}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


# ---------- CORE LOGIC ----------

def get_video_and_competitors(video_id: str):
    # 1️⃣ Video info
    v = yt("videos", {
        "part": "snippet,statistics",
        "id": video_id
    })["items"]

    if not v:
        return None

    video = v[0]
    title = video["snippet"]["title"]
    channel_title = video["snippet"]["channelTitle"]

    # asosiy keyword (oddiy, ammo samarali)
    keyword = title.split("|")[0].split("-")[0][:60]

    # 2️⃣ BITTA search.list — HAMMA ANALIZ SHU YERDA
    published_after = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    search = yt("search", {
        "part": "snippet",
        "type": "video",
        "q": keyword,
        "order": "viewCount",
        "maxResults": 25,
        "publishedAfter": published_after
    })["items"]

    competitors = []
    channels = {}
    used_titles = set()

    for item in search:
        vid = item["id"]["videoId"]
        sn = item["snippet"]

        # views olish
        stats = yt("videos", {
            "part": "statistics",
            "id": vid
        })["items"]

        if not stats:
            continue

        views = int(stats[0]["statistics"].get("viewCount", 0))
        t = sn["title"]

        if t.lower() in used_titles:
            continue

        used_titles.add(t.lower())

        competitors.append({
            "title": t,
            "views": views
        })

        ch = sn["channelTitle"]
        channels[ch] = channels.get(ch, 0) + 1

        if len(competitors) >= 10:
            break

    # sort views
    competitors.sort(key=lambda x: x["views"], reverse=True)

    return {
        "video_title": title,
        "channel": channel_title,
        "views": video["statistics"].get("viewCount"),
        "likes": video["statistics"].get("likeCount"),
        "comments": video["statistics"].get("commentCount"),
        "keyword": keyword,
        "competitors": competitors,
        "channels": sorted(channels.items(), key=lambda x: x[1], reverse=True)[:10]
    }


# ---------- HANDLERS ----------

@dp.message(CommandStart())
async def start(msg: Message):
    await msg.answer(
        "👋 Salom!\n"
        "YouTube video linkini yubor.\n\n"
        "Men:\n"
        "🧠 TOP nomlar (konkurent asosida)\n"
        "🏷 TOP taglar\n"
        "📺 Raqobatchi kanallar\n"
        "chiqarib beraman."
    )


@dp.message(F.text.startswith("http"))
async def handle_video(msg: Message):
    vid = extract_video_id(msg.text)
    if not vid:
        await msg.answer("❌ Video link noto‘g‘ri.")
        return

    wait = await msg.answer("⏳ Video analiz qilinmoqda, iltimos kuting...")

    try:
        data = await asyncio.to_thread(get_video_and_competitors, vid)
    except Exception as e:
        await wait.edit_text("❌ Video topilmadi yoki API cheklangan.")
        return

    if not data:
        await wait.edit_text("❌ Video topilmadi.")
        return

    text = (
        f"🎬 {data['video_title']}\n\n"
        f"👁 View: {data['views']}\n"
        f"👍 Like: {data['likes']}\n"
        f"💬 Comment: {data['comments']}\n\n"
        f"👇 Kerakli funksiyani tanlang:"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧠 TOP NOMLAR", callback_data=f"titles:{vid}"),
            InlineKeyboardButton(text="🏷 TOP TAGLAR", callback_data=f"tags:{vid}")
        ],
        [
            InlineKeyboardButton(text="📺 Raqobatchi kanallar", callback_data=f"channels:{vid}")
        ]
    ])

    await wait.edit_text(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("titles:"))
async def cb_titles(cb):
    vid = cb.data.split(":")[1]
    data = await asyncio.to_thread(get_video_and_competitors, vid)

    lines = []
    for i, c in enumerate(data["competitors"], 1):
        lines.append(f"{i}. {c['title']} — 👁 {c['views']:,}")

    await cb.message.answer(
        "🧠 OXIRGI 30 KUN — KONKURENT TOP NOMLARI:\n\n" + "\n".join(lines)
    )


@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(cb):
    vid = cb.data.split(":")[1]
    data = await asyncio.to_thread(get_video_and_competitors, vid)

    base = data["keyword"].lower().replace(",", "")
    tags = list(dict.fromkeys([
        base,
        "beamng drive",
        "mcqueen",
        "pixar cars",
        "truck challenge",
        "viral gameplay",
        "satisfying",
        "crash test",
        "cars toys",
        "kids cars"
    ]))

    await cb.message.answer(
        "🏷 TOP TAGLAR (copy-paste):\n\n" + ", ".join(tags)
    )


@dp.callback_query(F.data.startswith("channels:"))
async def cb_channels(cb):
    vid = cb.data.split(":")[1]
    data = await asyncio.to_thread(get_video_and_competitors, vid)

    lines = []
    for i, (ch, cnt) in enumerate(data["channels"], 1):
        lines.append(f"{i}. {ch} — {cnt} video")

    await cb.message.answer(
        "📺 RAQOBATCHI KANALLAR (TOP):\n\n" + "\n".join(lines)
    )


# ---------- RUN ----------

async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
