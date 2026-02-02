import os, re, asyncio, requests
from datetime import datetime, timedelta, timezone
from collections import Counter
from difflib import SequenceMatcher

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

# ================== UTILS ==================
def extract_video_id(url):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def yt(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=15
    )
    if r.status_code == 403:
        raise PermissionError("403")
    r.raise_for_status()
    return r.json()

def clean(t):
    return re.sub(r"[^\w\s]", "", t.lower()).strip()

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio() > 0.7

# ================== CORE ==================
def get_video(video_id):
    try:
        r = yt("videos", {
            "part": "snippet,statistics",
            "id": video_id
        })["items"]

        if not r:
            return None

        v = r[0]
        stat = v.get("statistics", {})
        return {
            "title": v["snippet"]["title"],
            "views": int(stat.get("viewCount", 0)),
            "likes": int(stat.get("likeCount", 0)),
            "comments": int(stat.get("commentCount", 0)),
        }

    except PermissionError:
        # KIDS / RESTRICTED fallback
        r = yt("videos", {
            "part": "snippet",
            "id": video_id
        })["items"]

        if not r:
            return None

        return {
            "title": r[0]["snippet"]["title"],
            "views": None,
            "likes": None,
            "comments": None,
        }

def competitor_titles(base_title):
    base = clean(base_title)
    seen = []
    out = []

    try:
        search = yt("search", {
            "part": "snippet",
            "q": base,
            "type": "video",
            "order": "viewCount",
            "maxResults": 50
        })
    except PermissionError:
        return []

    for it in search["items"]:
        vid = it["id"]["videoId"]

        try:
            v = yt("videos", {
                "part": "statistics,snippet",
                "id": vid
            })["items"]
        except PermissionError:
            continue

        if not v:
            continue

        title = v[0]["snippet"]["title"]
        views = int(v[0]["statistics"].get("viewCount", 0))

        if views < 1000:
            continue

        ct = clean(title)
        if any(similar(ct, s) for s in seen):
            continue

        seen.append(ct)
        out.append((title, views))

        if len(out) >= 10:
            break

    return out

def make_tags(title, competitors):
    words = []
    for t, _ in competitors:
        words += clean(t).split()
    words += clean(title).split()

    common = Counter(words).most_common(40)
    tags = [w for w, _ in common if len(w) > 3]

    base = ["gameplay", "challenge", "experiment", "viral", "cars", "truck"]
    for b in base:
        if b not in tags:
            tags.append(b)

    return ", ".join(tags[:30])

def competitor_channels(base_title):
    base = clean(base_title)
    chans = {}

    try:
        s = yt("search", {
            "part": "snippet",
            "q": base,
            "type": "video",
            "order": "viewCount",
            "maxResults": 25
        })
    except PermissionError:
        return []

    for it in s["items"]:
        cname = it["snippet"]["channelTitle"]
        chans[cname] = chans.get(cname, 0) + 1

    return sorted(chans.items(), key=lambda x: x[1], reverse=True)[:5]

# ================== HANDLERS ==================
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "YouTube video havolasini yuboring.\n\n"
        "🧠 TOP nomlar\n"
        "🏷 TOP taglar\n"
        "📺 Raqobatchi kanallar"
    )

@dp.message(F.text.startswith("http"))
async def handle(msg: Message):
    vid = extract_video_id(msg.text)
    if not vid:
        return await msg.answer("❌ Noto‘g‘ri link.")

    data = await asyncio.to_thread(get_video, vid)
    if not data:
        return await msg.answer("❌ Video topilmadi.")

    views = f"{data['views']:,}" if data["views"] is not None else "—"
    likes = f"{data['likes']:,}" if data["likes"] is not None else "—"
    comm = f"{data['comments']:,}" if data["comments"] is not None else "—"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧠 TOP NOMLAR", callback_data=f"t:{vid}"),
            InlineKeyboardButton(text="🏷 TOP TAGLAR", callback_data=f"g:{vid}")
        ],
        [
            InlineKeyboardButton(text="📺 Raqobatchi kanallar", callback_data=f"c:{vid}")
        ]
    ])

    await msg.answer(
        f"🎬 <b>{data['title']}</b>\n"
        f"👁 {views} | 👍 {likes} | 💬 {comm}\n\n"
        "👇 Funksiyani tanlang:",
        reply_markup=kb
    )

@dp.callback_query()
async def callbacks(cb: CallbackQuery):
    action, vid = cb.data.split(":")
    wait = await cb.message.answer("⏳ Analiz olinmoqda...")

    try:
        base = (await asyncio.to_thread(get_video, vid))["title"]

        if action == "t":
            res = await asyncio.to_thread(competitor_titles, base)
            if not res:
                return await cb.message.answer("⚠️ O‘xshash konkurent nomlar topilmadi.")

            text = "🧠 <b>TOP KONKURENT NOMLAR:</b>\n\n"
            for i, (t, v) in enumerate(res, 1):
                text += f"{i}. {t}\n👁 {v:,}\n\n"
            await cb.message.answer(text)

        elif action == "g":
            comps = await asyncio.to_thread(competitor_titles, base)
            tags = await asyncio.to_thread(make_tags, base, comps)
            await cb.message.answer(f"🏷 <b>TOP TAGLAR:</b>\n\n<code>{tags}</code>")

        elif action == "c":
            chans = await asyncio.to_thread(competitor_channels, base)
            if not chans:
                return await cb.message.answer("⚠️ Raqobatchi kanallar topilmadi.")

            text = "📺 <b>RAQOBATCHI KANALLAR:</b>\n\n"
            for i, (c, n) in enumerate(chans, 1):
                text += f"{i}. {c} — {n} video\n"
            await cb.message.answer(text)

    finally:
        await wait.delete()
        await cb.answer()

# ================== RUN ==================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
