import os, re, asyncio, requests
from difflib import SequenceMatcher
from collections import Counter

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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

# ================= YOUTUBE API =================
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

# ================= TEXT UTILS =================
def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def clean(t):
    return re.sub(r"[^\w\s]", "", t).strip()

def words(t):
    return re.findall(r"[a-zA-Z]{3,}", t.lower())

# ================= VIDEO TYPE =================
def detect_type(title):
    t = title.lower()
    if any(x in t for x in ["beamng", "gameplay", "vs", "challenge", "experiment"]):
        return "gaming"
    if any(x in t for x in ["unboxing", "review", "toys", "cars", "mcqueen", "pixar"]):
        return "unboxing"
    if any(x in t for x in ["lyrics", "song", "music"]):
        return "music"
    return "general"

# ================= SEARCH =================
def search_titles(keyword):
    data = yt("search", {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "maxResults": 25
    })
    return [v["snippet"]["title"] for v in data.get("items", [])]

# ================= FALLBACK CTR TITLES =================
def fallback_titles(base, vtype):
    if vtype == "unboxing":
        return [
            f"{base} – Is It Really Worth It?",
            f"I Tested {base} – Here’s What Happened",
            f"{base} Review After Real Use",
            f"{base} – Honest Review (No Hype)",
            f"{base} – Pros & Cons Explained"
        ]

    if vtype == "gaming":
        return [
            f"{base} – This Went Wrong",
            f"I Tried This in {base}…",
            f"{base} – Unexpected Result",
            f"{base} Gameplay That Shocked Me",
            f"{base} – Worst vs Best Moment"
        ]

    if vtype == "music":
        return [
            f"{base} | English Lyrics",
            f"{base} | Viral TikTok Version",
            f"{base} – Emotional Version",
            f"{base} Lyrics Everyone Is Searching For",
            f"{base} | Most Played Song"
        ]

    return [
        f"{base} – What Happened?",
        f"{base} – Nobody Expected This",
        f"{base} – Full Breakdown",
        f"{base} – The Truth",
        f"{base} – Explained"
    ]

# ================= MAIN TITLE GENERATOR =================
def generate_top_titles(original_title):
    base = clean(original_title)
    vtype = detect_type(base)

    search_results = search_titles(base)
    results = []

    for t in search_results:
        ct = clean(t)

        if similarity(base, ct) > 0.92:
            continue

        if len(ct) > 75:
            ct = ct[:72] + "..."

        if all(similarity(ct, r) < 0.8 for r in results):
            results.append(ct)

        if len(results) >= 5:
            break

    # FALLBACK
    if len(results) < 3:
        results = fallback_titles(base, vtype)

    return results

# ================= HANDLERS =================
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "YouTube video havolasini yuboring.\n\n"
        "🧠 TOP NOMLAR — YouTube search + analiz\n"
        "🏷 CTR oshiruvchi nomlar\n"
        "❌ Qotmaydi, ❌ topilmadi chiqmaydi"
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
        await msg.answer("❌ Video topilmadi yoki API cheklangan.")
        return

    title = data["snippet"]["title"]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 TOP NOMLAR",
                    callback_data=f"title:{vid}"
                )
            ]
        ]
    )

    await msg.answer(
        f"🎬 <b>{title}</b>\n\n"
        "👇 TOP NOMLARNI olish uchun bosing:",
        reply_markup=kb
    )

# ================= CALLBACK =================
@dp.callback_query(F.data.startswith("title:"))
async def cb_title(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    data = yt("videos", {"part": "snippet", "id": vid})["items"][0]

    titles = generate_top_titles(data["snippet"]["title"])

    text = "🧠 <b>ANALIZ ASOSIDA TOP NOMLAR:</b>\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n"

    await cb.message.answer(text)
    await cb.answer()

# ================= RUN =================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
