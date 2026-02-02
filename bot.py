import os
import re
import asyncio
import requests
from collections import Counter

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ================= UTILS =================
def extract_video_id(url: str):
    patterns = [
        r"v=([^&]+)",
        r"youtu\.be/([^?]+)",
        r"youtube\.com/shorts/([^?]+)",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def yt_api(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=8
    )
    r.raise_for_status()
    return r.json()


# ================= AI TITLE (CTR LOGIC) =================
def ai_titles(title: str):
    base = title.split("|")[0].strip()

    return [
        f"{base} 😱 INSANE Result Nobody Expected",
        f"I Tested {base}… The Result SHOCKED Me",
        f"{base} 🚨 This Went Completely Wrong",
        f"{base} | The Craziest Outcome Ever",
        f"{base} 🔥 You Won’t Believe the Ending",
    ]


# ================= AI TAGS (SEMANTIC + COMPETITOR) =================
def ai_tags(video_title: str, competitor_channels: list[str]):
    t = video_title.lower()
    tags = set()

    # Core topic
    if "beamng" in t:
        tags |= {
            "beamng drive", "beamng gameplay", "beamng mods",
            "beamng crash", "beamng simulation"
        }

    if "truck" in t or "flatbed" in t:
        tags |= {
            "flatbed truck", "truck challenge",
            "truck experiment", "truck vs car"
        }

    if "mcqueen" in t or "cars" in t:
        tags |= {
            "pixar cars", "lightning mcqueen",
            "disney cars", "cars gameplay"
        }

    # Competitor channel names → keyword signal
    for ch in competitor_channels:
        words = ch.lower().split()
        for w in words:
            if len(w) > 3:
                tags.add(w)

    # CTR / Search helpers
    tags |= {
        "viral gameplay", "trending video",
        "satisfying crash", "realistic physics",
        "gaming shorts", "youtube gaming"
    }

    return ", ".join(sorted(tags))


# ================= COMPETITOR ANALYSIS (REAL TOP) =================
def competitor_channels(keyword: str):
    data = yt_api(
        "search",
        {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "maxResults": 25,
        }
    )

    channels = []
    for item in data.get("items", []):
        channels.append(item["snippet"]["channelTitle"])

    counter = Counter(channels)
    top = counter.most_common(5)

    return top


# ================= HANDLERS =================
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "🔗 YouTube video havolasini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 <b>TOP NOMLAR</b>\n"
        "🏷 <b>TOP TAGLAR</b>\n"
        "🎯 <b>Raqobatchi kanallar (TOP)</b>\n\n"
        "aniq va qotmaydigan analiz beraman."
    )


@dp.message(F.text.startswith("http"))
async def handle_video(msg: Message):
    video_id = extract_video_id(msg.text)
    if not video_id:
        await msg.answer("❌ Video havolasi noto‘g‘ri.")
        return

    try:
        video = yt_api(
            "videos",
            {"part": "snippet,statistics", "id": video_id}
        )["items"][0]
    except Exception:
        await msg.answer("❌ Video topilmadi yoki API cheklangan.")
        return

    s = video["snippet"]
    st = video["statistics"]

    text = (
        f"🎬 <b>{s['title']}</b>\n"
        f"📺 Kanal: <b>{s['channelTitle']}</b>\n\n"
        f"👁 View: {st.get('viewCount','-')}\n"
        f"👍 Like: {st.get('likeCount','-')}\n"
        f"💬 Comment: {st.get('commentCount','-')}\n\n"
        "👇 <b>Kerakli funksiyani tanlang:</b>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 TOP NOMLAR",
                    callback_data=f"title:{video_id}"
                ),
                InlineKeyboardButton(
                    text="🏷 TOP TAGLAR",
                    callback_data=f"tags:{video_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎯 Raqobatchi kanallar",
                    callback_data=f"comp:{video_id}"
                )
            ],
        ]
    )

    await msg.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("title:"))
async def cb_title(cb: CallbackQuery):
    await cb.answer()
    vid = cb.data.split(":")[1]

    video = yt_api("videos", {"part": "snippet", "id": vid})["items"][0]
    titles = ai_titles(video["snippet"]["title"])

    text = "<b>🧠 TOP CLICKBAIT NOMLAR:</b>\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n"

    await cb.message.answer(text)


@dp.callback_query(F.data.startswith("comp:"))
async def cb_comp(cb: CallbackQuery):
    await cb.answer()
    vid = cb.data.split(":")[1]

    video = yt_api("videos", {"part": "snippet", "id": vid})["items"][0]
    keyword = video["snippet"]["title"].split("|")[0]

    top_channels = await asyncio.to_thread(competitor_channels, keyword)

    text = "🎯 <b>Raqobatchi kanallar (TOP)</b>\n\n"
    for i, (ch, count) in enumerate(top_channels, 1):
        text += f"{i}. <b>{ch}</b>\n   🎬 O‘xshash videolar: {count}\n"

    text += "\n🚀 <b>Ko‘p chiqayotgan kanallar — real raqobatchilar</b>"

    await cb.message.answer(text)


@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(cb: CallbackQuery):
    await cb.answer()
    vid = cb.data.split(":")[1]

    video = yt_api("videos", {"part": "snippet", "id": vid})["items"][0]
    keyword = video["snippet"]["title"].split("|")[0]

    competitors = await asyncio.to_thread(competitor_channels, keyword)
    competitor_names = [c[0] for c in competitors]

    tags = ai_tags(video["snippet"]["title"], competitor_names)

    await cb.message.answer(
        "<b>🏷 TOP TAGLAR (copy-paste):</b>\n\n"
        f"<code>{tags}</code>"
    )


# ================= RUN =================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
