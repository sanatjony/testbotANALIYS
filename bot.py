import os, re, asyncio, requests
from collections import Counter, defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ================== YOUTUBE API ==================
def yt(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=8
    )
    r.raise_for_status()
    return r.json()

def extract_video_id(url):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def clean_words(text):
    return re.findall(r"[a-zA-Z]{3,}", text.lower())

# ================== VIDEO TYPE ==================
def detect_video_type(title, desc):
    t = f"{title} {desc}".lower()

    if any(x in t for x in ["beamng", "gameplay", "vs", "challenge", "experiment"]):
        return "gaming"
    if any(x in t for x in ["lyrics", "song", "music", "tiktok"]):
        return "music"
    if any(x in t for x in ["cars", "mcqueen", "pixar", "toys", "unboxing"]):
        return "entertainment"
    if any(x in t for x in ["how to", "tutorial", "guide"]):
        return "education"

    return "general"

# ================== COMPETITOR ANALYSIS ==================
def competitor_videos(keyword):
    data = yt("search", {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "maxResults": 25
    })
    return data.get("items", [])

def competitor_channels(videos):
    channels = defaultdict(int)
    for v in videos:
        ch = v["snippet"]["channelTitle"]
        channels[ch] += 1
    return sorted(channels.items(), key=lambda x: x[1], reverse=True)[:5]

def hot_keywords(videos):
    words = []
    for v in videos:
        words += clean_words(v["snippet"]["title"])
    return [w for w, _ in Counter(words).most_common(12)]

# ================== AI TITLE LOGIC ==================
def generate_titles(base_title, vtype, hot):
    base = base_title.split("|")[0].strip()

    if vtype == "entertainment":
        return [
            f"{base} 😱 INSANE Result!",
            f"{base} 🔥 You Won’t Believe This!",
            f"{base} 🤯 CRAZY Cars Moment",
            f"{base} 😲 Unexpected Outcome",
            f"{base} 🚗 Most Satisfying Cars Video"
        ]

    if vtype == "gaming":
        return [
            f"{base} 🎮 INSANE Gameplay",
            f"{base} 💥 This Went Wrong",
            f"{base} 🔥 CRAZY Experiment",
            f"{base} 😱 Unexpected Result",
            f"{base} 🚨 SHOCKING Ending"
        ]

    if vtype == "music":
        return [
            f"{base} | English Lyrics",
            f"{base} | TikTok Viral Version",
            f"{base} | Emotional Version",
            f"{base} Lyrics (Trending)",
            f"{base} | Most Played Song"
        ]

    return [
        f"{base} | Trending Now",
        f"{base} – What Happened?",
        f"{base} | Unexpected Moment",
        f"{base} | Viral Video",
        f"{base} – Full Experience"
    ]

# ================== AI TAG LOGIC ==================
def generate_tags(title, hot):
    tags = list(dict.fromkeys(clean_words(title) + hot))
    return ", ".join(tags[:30])

# ================== HANDLERS ==================
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "YouTube video linkini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 TOP NOMLAR\n"
        "🏷 TOP TAGLAR\n"
        "📊 Raqobatchi kanallar\n"
        "ni analiz qilib beraman."
    )

@dp.message(F.text.startswith("http"))
async def handle_video(msg: Message):
    vid = extract_video_id(msg.text)
    if not vid:
        await msg.answer("❌ Link noto‘g‘ri.")
        return

    try:
        data = yt("videos", {"part": "snippet,statistics", "id": vid})["items"][0]
    except:
        await msg.answer("❌ Video topilmadi yoki API cheklangan.")
        return

    title = data["snippet"]["title"]
    views = data["statistics"].get("viewCount", "—")
    likes = data["statistics"].get("likeCount", "—")
    comments = data["statistics"].get("commentCount", "—")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 TOP NOMLAR",
                    callback_data=f"title:{vid}"
                ),
                InlineKeyboardButton(
                    text="🏷 TOP TAGLAR",
                    callback_data=f"tags:{vid}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Raqobatchi kanallar",
                    callback_data=f"comp:{vid}"
                )
            ]
        ]
    )

    await msg.answer(
        f"🎬 <b>{title}</b>\n\n"
        f"👁 View: {views}\n"
        f"👍 Like: {likes}\n"
        f"💬 Comment: {comments}\n\n"
        "👇 Kerakli funksiyani tanlang:",
        reply_markup=kb
    )

# ================== CALLBACKS ==================
@dp.callback_query(F.data.startswith("title:"))
async def cb_title(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    data = yt("videos", {"part": "snippet", "id": vid})["items"][0]

    title = data["snippet"]["title"]
    desc = data["snippet"].get("description", "")

    vtype = detect_video_type(title, desc)
    videos = competitor_videos(title)
    hot = hot_keywords(videos)

    titles = generate_titles(title, vtype, hot)

    text = "🧠 <b>ANALIZ ASOSIDA TOP NOMLAR:</b>\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n"

    await cb.message.answer(text)
    await cb.answer()

@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    data = yt("videos", {"part": "snippet", "id": vid})["items"][0]

    title = data["snippet"]["title"]
    videos = competitor_videos(title)
    hot = hot_keywords(videos)

    tags = generate_tags(title, hot)

    await cb.message.answer(
        "🏷 <b>TOP TAGLAR (copy–paste):</b>\n\n"
        f"<code>{tags}</code>"
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("comp:"))
async def cb_comp(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    data = yt("videos", {"part": "snippet", "id": vid})["items"][0]

    title = data["snippet"]["title"]
    videos = competitor_videos(title)
    channels = competitor_channels(videos)

    text = "📊 <b>Raqobatchi kanallar (TOP):</b>\n\n"
    for i, (ch, cnt) in enumerate(channels, 1):
        text += f"{i}. {ch} — o‘xshash video: {cnt}\n"

    await cb.message.answer(text)
    await cb.answer()

# ================== RUN ==================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
