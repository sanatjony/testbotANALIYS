import os, re, asyncio, requests
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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
        timeout=10
    )
    r.raise_for_status()
    return r.json()

def extract_video_id(url):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

# ================== TEXT UTILS ==================
def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def clean(text):
    return re.sub(r"[^\w\s]", "", text).strip()

# ================== DATE ==================
def is_last_30_days(published):
    published_date = datetime.strptime(published, "%Y-%m-%dT%H:%M:%SZ")
    return published_date >= datetime.utcnow() - timedelta(days=30)

# ================== MAIN LOGIC ==================
def get_competitor_top_titles(keyword):
    search = yt("search", {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "viewCount",
        "maxResults": 50
    })

    titles = []

    for item in search.get("items", []):
        vid = item["id"]["videoId"]
        snippet = item["snippet"]

        if not is_last_30_days(snippet["publishedAt"]):
            continue

        video_data = yt("videos", {
            "part": "statistics,snippet",
            "id": vid
        })["items"]

        if not video_data:
            continue

        views = int(video_data[0]["statistics"].get("viewCount", 0))
        if views < 1000:
            continue

        title = clean(video_data[0]["snippet"]["title"])

        # DUPLICATE CHECK
        if any(similarity(title, t) > 0.9 for t in titles):
            continue

        titles.append(title)

        if len(titles) >= 10:
            break

    return titles

# ================== HANDLERS ==================
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "YouTube video havolasini yuboring.\n\n"
        "🧠 TOP NOMLAR — konkurent kanallar analizi\n"
        "📊 Oxirgi 30 kun + eng ko‘p ko‘rilgan\n"
        "❌ Random emas, REAL"
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
                    text="🧠 TOP NOMLAR (Konkurent)",
                    callback_data=f"top:{vid}"
                )
            ]
        ]
    )

    await msg.answer(
        f"🎬 <b>{title}</b>\n\n"
        "👇 Konkurentlar asosida TOP nomlarni olish:",
        reply_markup=kb
    )

# ================== CALLBACK ==================
@dp.callback_query(F.data.startswith("top:"))
async def cb_top(cb: CallbackQuery):
    vid = cb.data.split(":")[1]

    data = yt("videos", {"part": "snippet", "id": vid})["items"][0]
    base_title = clean(data["snippet"]["title"])

    titles = get_competitor_top_titles(base_title)

    if not titles:
        await cb.message.answer("⚠️ Konkurentlardan yetarli ma’lumot topilmadi.")
        await cb.answer()
        return

    text = "🧠 <b>OXIRGI 30 KUN — KONKURENTLAR TOP NOMLARI:</b>\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n"

    await cb.message.answer(text)
    await cb.answer()

# ================== RUN ==================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
