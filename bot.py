import os, re, asyncio, requests
from datetime import datetime, timedelta
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

# ================= YOUTUBE HELPERS =================
def yt(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=20
    )
    r.raise_for_status()
    return r.json()

def extract_video_id(url):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def clean(text):
    return re.sub(r"[^\w\s]", "", text).lower().strip()

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def is_recent(date_str, days):
    d = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
    return d >= datetime.utcnow() - timedelta(days=days)

# ================= ANALYTICS =================
def get_video_basic(video_id):
    data = yt("videos", {
        "part": "snippet,statistics",
        "id": video_id
    })["items"]

    if not data:
        return None

    s = data[0]
    return {
        "title": s["snippet"]["title"],
        "channel_id": s["snippet"]["channelId"],
        "channel_title": s["snippet"]["channelTitle"],
        "views": int(s["statistics"].get("viewCount", 0)),
        "likes": int(s["statistics"].get("likeCount", 0)),
        "comments": int(s["statistics"].get("commentCount", 0)),
    }

# ================= TOP COMPETITOR TITLES =================
def competitor_top_titles(base_title):
    base = clean(base_title)
    words = base.split()

    queries = list(dict.fromkeys([
        base,
        " ".join(words[:5]),
        " ".join(words[:4]),
        " ".join(words[:3]),
        f"{words[0]} gameplay",
        f"{words[0]} truck",
        f"{words[0]} mcqueen",
        "beamng truck",
        "flatbed truck"
    ]))

    results = []

    for days in [60, 90]:
        for q in queries:
            search = yt("search", {
                "part": "snippet",
                "q": q,
                "type": "video",
                "order": "viewCount",
                "maxResults": 50
            })

            for item in search.get("items", []):
                vid = item["id"]["videoId"]
                sn = item["snippet"]

                if not is_recent(sn["publishedAt"], days):
                    continue

                v = yt("videos", {
                    "part": "statistics,snippet",
                    "id": vid
                })["items"]

                if not v:
                    continue

                views = int(v[0]["statistics"].get("viewCount", 0))
                if views < 100:
                    continue

                title = v[0]["snippet"]["title"]
                ct = clean(title)

                if any(similarity(ct, clean(r["title"])) > 0.7 for r in results):
                    continue

                results.append({
                    "title": title,
                    "views": views,
                    "channel": v[0]["snippet"]["channelTitle"]
                })

                if len(results) >= 10:
                    return sorted(results, key=lambda x: x["views"], reverse=True)

    return sorted(results, key=lambda x: x["views"], reverse=True)

# ================= TAG GENERATOR =================
def generate_tags(title, competitors):
    words = []
    for t in [title] + [c["title"] for c in competitors]:
        words += clean(t).split()

    common = Counter(words).most_common(25)

    tags = []
    for w, _ in common:
        if len(w) > 3 and w not in tags:
            tags.append(w)

    # semantic extensions
    extra = ["gameplay", "challenge", "experiment", "truck", "cars", "viral", "satisfying"]
    for e in extra:
        if e not in tags:
            tags.append(e)

    return ", ".join(tags[:30])

# ================= COMPETITOR CHANNELS =================
def competitor_channels(base_title):
    base = clean(base_title)
    channels = {}

    search = yt("search", {
        "part": "snippet",
        "q": base,
        "type": "video",
        "order": "viewCount",
        "maxResults": 50
    })

    for item in search.get("items", []):
        cid = item["snippet"]["channelId"]
        cname = item["snippet"]["channelTitle"]
        channels[cid] = cname

    results = []
    for cid, cname in channels.items():
        ch_vids = yt("search", {
            "part": "id",
            "channelId": cid,
            "type": "video",
            "maxResults": 10
        })["items"]

        results.append({
            "channel": cname,
            "count": len(ch_vids)
        })

    return sorted(results, key=lambda x: x["count"], reverse=True)[:5]

# ================= HANDLERS =================
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "YouTube video linkini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 TOP nomlar (konkurentlardan)\n"
        "🏷 TOP taglar\n"
        "📺 Raqobatchi kanallar\n"
        "chiqarib beraman."
    )

@dp.message(F.text.startswith("http"))
async def handle_video(msg: Message):
    vid = extract_video_id(msg.text)
    if not vid:
        await msg.answer("❌ Link noto‘g‘ri.")
        return

    data = get_video_basic(vid)
    if not data:
        await msg.answer("❌ Video topilmadi.")
        return

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
        f"🎬 <b>{data['title']}</b>\n\n"
        f"👁 {data['views']:,} | 👍 {data['likes']:,} | 💬 {data['comments']:,}\n\n"
        "👇 Kerakli funksiyani tanlang:",
        reply_markup=kb
    )

# -------- TOP TITLES
@dp.callback_query(F.data.startswith("titles:"))
async def cb_titles(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    wait = await cb.message.answer("⏳ Konkurent nomlar analiz qilinmoqda...")

    base = get_video_basic(vid)["title"]
    tops = competitor_top_titles(base)

    await wait.delete()

    if not tops:
        await cb.message.answer("⚠️ Yetarli ma’lumot topilmadi.")
        return

    text = "🧠 <b>OXIRGI 60–90 KUN — TOP KONKURENT NOMLAR:</b>\n\n"
    for i, t in enumerate(tops, 1):
        text += f"{i}. {t['title']}\n   👁 {t['views']:,}\n\n"

    await cb.message.answer(text)
    await cb.answer()

# -------- TAGS
@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    wait = await cb.message.answer("⏳ TOP taglar tayyorlanmoqda...")

    base = get_video_basic(vid)["title"]
    competitors = competitor_top_titles(base)
    tags = generate_tags(base, competitors)

    await wait.delete()

    await cb.message.answer(
        "🏷 <b>TOP TAGLAR (copy-paste):</b>\n\n"
        f"<code>{tags}</code>"
    )
    await cb.answer()

# -------- CHANNELS
@dp.callback_query(F.data.startswith("channels:"))
async def cb_channels(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    wait = await cb.message.answer("⏳ Raqobatchi kanallar analiz qilinmoqda...")

    base = get_video_basic(vid)["title"]
    chans = competitor_channels(base)

    await wait.delete()

    if not chans:
        await cb.message.answer("⚠️ Kanal ma’lumotlari topilmadi.")
        return

    text = "📺 <b>RAQOBATCHI KANALLAR (TOP):</b>\n\n"
    for i, c in enumerate(chans, 1):
        text += f"{i}. {c['channel']}\n   🎞 O‘xshash video: {c['count']}\n\n"

    await cb.message.answer(text)
    await cb.answer()

# ================= RUN =================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
