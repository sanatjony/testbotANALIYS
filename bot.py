import os, re, asyncio, requests
from collections import Counter

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ------------------ HELPERS ------------------
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

def words(text):
    return re.findall(r"[a-zA-Z]{3,}", text.lower())

# ------------------ TYPE DETECT ------------------
def detect_type(title, desc):
    t = f"{title} {desc}".lower()

    if any(x in t for x in ["beamng", "gameplay", "vs", "challenge"]):
        return "gaming"
    if any(x in t for x in ["lyrics", "song", "music"]):
        return "music"
    if any(x in t for x in ["cars", "mcqueen", "pixar", "toys", "unboxing"]):
        return "entertainment"
    if any(x in t for x in ["how to", "tutorial", "guide"]):
        return "education"

    return "general"

# ------------------ COMPETITOR TITLES ------------------
def competitor_titles(keyword):
    data = yt("search", {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "maxResults": 20
    })
    return [i["snippet"]["title"] for i in data.get("items", [])]

def strong_words(titles):
    all_words = []
    for t in titles:
        all_words += words(t)
    return [w for w, _ in Counter(all_words).most_common(10)]

# ------------------ TITLE AI ------------------
def generate_titles(title, vtype, hot):
    base = title.split("|")[0].strip()

    if vtype == "entertainment":
        return [
            f"{base} 😱 INSANE Result!",
            f"{base} 🔥 You Won’t Believe This!",
            f"{base} 🤯 CRAZY Experiment",
            f"{base} 😲 Unexpected Outcome",
            f"{base} 🚗 Most Satisfying Cars Moment"
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

    if vtype == "education":
        return [
            f"How to {base}",
            f"{base} Explained Simply",
            f"{base} Step-by-Step Guide",
            f"{base} for Beginners",
            f"{base} Full Tutorial"
        ]

    return [
        f"{base} | {hot[0].title()}",
        f"{base} – What Happened?",
        f"{base} | Unexpected Moment",
        f"{base} | Trending Now",
        f"{base} – Full Experience"
    ]

# ------------------ TAG AI ------------------
def generate_tags(title, hot):
    tags = list(dict.fromkeys(words(title) + hot))
    return ", ".join(tags[:30])

# ------------------ HANDLERS ------------------
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "YouTube video linkini yuboring.\n"
        "Men sizga:\n"
        "🧠 TOP NOMLAR\n"
        "🏷 TOP TAGLAR\n"
        "ni real analiz asosida beraman."
    )

@dp.message(F.text.startswith("http"))
async def handle_video(msg: Message):
    vid = extract_video_id(msg.text)
    if not vid:
        await msg.answer("❌ Link noto‘g‘ri.")
        return

    try:
        data = yt("videos", {"part": "snippet", "id": vid})["items"][0]
    except:
        await msg.answer("❌ Video topilmadi.")
        return

    title = data["snippet"]["title"]
    desc = data["snippet"].get("description", "")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton("🧠 TOP NOMLAR", callback_data=f"title:{vid}"),
                InlineKeyboardButton("🏷 TOP TAGLAR", callback_data=f"tags:{vid}")
            ]
        ]
    )

    await msg.answer(
        f"🎬 <b>{title}</b>\n\n"
        "👇 Funksiyani tanlang:",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("title:"))
async def cb_title(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    data = yt("videos", {"part": "snippet", "id": vid})["items"][0]

    title = data["snippet"]["title"]
    desc = data["snippet"].get("description", "")

    vtype = detect_type(title, desc)
    comps = competitor_titles(title)
    hot = strong_words(comps)

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
    comps = competitor_titles(title)
    hot = strong_words(comps)

    tags = generate_tags(title, hot)

    await cb.message.answer(
        "🏷 <b>TOP TAGLAR (copy-paste):</b>\n\n"
        f"<code>{tags}</code>"
    )
    await cb.answer()

# ------------------ RUN ------------------
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
