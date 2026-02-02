import os
import re
import asyncio
import requests
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


# ================= AI LOGIC =================
def ai_titles(title: str):
    base = title.split("|")[0].strip()
    return [
        f"{base} 😱 INSANE Result!",
        f"{base} 🔥 You Won’t Believe This",
        f"{base} 💥 CRAZY Moment",
        f"{base} ⚠️ Unexpected Outcome",
        f"{base} 🚀 SHOCKING Video",
    ]


def ai_tags(title: str):
    t = title.lower()
    tags = set()

    if "mcqueen" in t or "cars" in t:
        tags |= {
            "pixar cars", "lightning mcqueen", "disney cars",
            "cars toys", "mcqueen video"
        }

    if "truck" in t:
        tags |= {
            "flatbed truck", "truck challenge",
            "truck experiment", "truck gameplay"
        }

    if "lyrics" in t or "song" in t:
        tags |= {
            "viral song", "tiktok song", "english lyrics",
            "lyrics video", "viral music"
        }

    tags |= {
        "viral video", "youtube shorts",
        "trending video", "popular video"
    }

    return ", ".join(sorted(tags))


def global_trend_score(title: str):
    """
    Grafik yo‘q.
    Tezkor baho (heuristic).
    """
    score = 0
    t = title.lower()

    if "viral" in t or "tiktok" in t:
        score += 2
    if "mcqueen" in t or "cars" in t:
        score += 1
    if "lyrics" in t:
        score += 1

    if score >= 3:
        return "🟢 O‘sishda"
    elif score == 2:
        return "🟡 Barqaror"
    else:
        return "🔴 Past"


def competitor_analysis(keyword: str):
    data = yt_api(
        "search",
        {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "maxResults": 25,
        }
    )

    channels = set()
    for item in data.get("items", []):
        channels.add(item["snippet"]["channelTitle"])

    return {
        "videos": len(data.get("items", [])),
        "channels": len(channels),
    }


# ================= HANDLERS =================
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "🔗 YouTube video havolasini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 <b>TOP NOMLAR</b>\n"
        "🏷 <b>TOP TAGLAR</b>\n"
        "📊 <b>Raqobat analizi</b>\n"
        "📈 <b>Global trend (1 oy)</b>\n\n"
        "chiqarib beraman."
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
                    text="📊 Raqobat",
                    callback_data=f"comp:{video_id}"
                ),
                InlineKeyboardButton(
                    text="📈 Global trend",
                    callback_data=f"trend:{video_id}"
                ),
            ],
        ]
    )

    await msg.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("title:"))
async def cb_title(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    video = yt_api("videos", {"part": "snippet", "id": vid})["items"][0]
    titles = ai_titles(video["snippet"]["title"])

    text = "<b>🧠 TOP CLICKBAIT NOMLAR:</b>\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n"

    await cb.message.answer(text)


@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    video = yt_api("videos", {"part": "snippet", "id": vid})["items"][0]
    tags = ai_tags(video["snippet"]["title"])

    await cb.message.answer(
        "<b>🏷 TOP TAGLAR (copy-paste):</b>\n\n"
        f"<code>{tags}</code>"
    )


@dp.callback_query(F.data.startswith("trend:"))
async def cb_trend(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    video = yt_api("videos", {"part": "snippet", "id": vid})["items"][0]
    title = video["snippet"]["title"]

    result = global_trend_score(title)
    await cb.message.answer(
        f"📈 <b>Global trend (1 oy)</b>\n"
        f"🔑 Keyword: <b>{title.split('|')[0]}</b>\n"
        f"📊 Natija: {result}"
    )


@dp.callback_query(F.data.startswith("comp:"))
async def cb_comp(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    video = yt_api("videos", {"part": "snippet", "id": vid})["items"][0]
    keyword = video["snippet"]["title"].split("|")[0]

    data = await asyncio.to_thread(competitor_analysis, keyword)

    await cb.message.answer(
        "📊 <b>Raqobat (YouTube Search)</b>\n\n"
        f"🔑 Keyword: <b>{keyword}</b>\n"
        f"🎬 Top videolar: {data['videos']}\n"
        f"📺 Turli kanallar: {data['channels']}\n\n"
        f"📌 Xulosa: "
        f"{'🔴 Raqobat yuqori' if data['channels'] > 10 else '🟢 Raqobat past'}"
    )


# ================= RUN =================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
