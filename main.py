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
