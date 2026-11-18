import asyncio, aiohttp, re
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

TOKEN = os.environ["TOKEN"]
BASE_URL = os.environ["RENDER_EXTERNAL_URL"]
PATH = "/webhook"

bot = Bot(TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("Привет! Я OSINT-бот.")

SITES = {
    "GitHub": "https://github.com/{}",
    "Pinterest": "https://www.pinterest.com/{}/",
    "SoundCloud": "https://soundcloud.com/{}",
    "Behance": "https://www.behance.net/{}",
    "Dribbble": "https://dribbble.com/{}",
    "Dev.to": "https://dev.to/{}",
}

@dp.message(Command("nick"))
async def nick(m: Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2 or not re.fullmatch(r"[\w.\-]{1,32}", parts[1].strip()):
        await m.answer("Напиши так: /nick username")
        return
    name = parts[1].strip()
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as s:
        async def check(site, tpl):
            url = tpl.format(name)
            try:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    return site, url, r.status == 200
            except Exception:
                return site, url, False
        results = await asyncio.gather(*(check(k, v) for k, v in SITES.items()))
    found = [f"✅ {site}: {url}" for site, url, ok in results if ok]
    await m.answer("\n".join(found) if found else "Ничего не найдено")
async def on_startup(bot: Bot):
    await bot.set_webhook(BASE_URL + PATH)

dp.startup.register(on_startup)

async def health(request):
    return web.Response(text="ok")

app = web.Application()
app.router.add_get("/", health)
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=PATH)
setup_application(app, dp, bot=bot)

web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
