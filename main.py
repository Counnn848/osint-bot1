import ipaddress
import phonenumbers
from phonenumbers import geocoder, carrier, timezone
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
@dp.message(Command("phone"))
async def phone(m: Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await m.answer("Напиши так: /phone +79991234567")
        return
    try:
        num = phonenumbers.parse(parts[1].strip(), None)
    except Exception:
        await m.answer("Не понял номер. Пиши в международном формате: +79991234567")
        return
    if not phonenumbers.is_valid_number(num):
        await m.answer("Такого номера не существует")
        return
    country = geocoder.description_for_number(num, "ru") or "неизвестно"
    oper = carrier.name_for_number(num, "ru") or "неизвестно"
    tz = ", ".join(timezone.time_zones_for_number(num))
    fmt = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    await m.answer(f"📱 {fmt}\n🌍 Регион: {country}\n📡 Оператор: {oper}\n🕒 Часовой пояс: {tz}")

@dp.message(Command("ip"))
async def ip_info(m: Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await m.answer("Напиши так: /ip 8.8.8.8")
        return
    try:
        ip = ipaddress.ip_address(parts[1].strip())
    except ValueError:
        await m.answer("Это не похоже на IP-адрес")
        return
    if not ip.is_global:
        await m.answer("Это локальный адрес, по нему данных нет")
        return
    url = f"http://ip-api.com/json/{ip}?lang=ru&fields=status,country,regionName,city,timezone,isp,org,as,proxy,hosting"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                d = await r.json()
    except Exception:
        await m.answer("Сервис не ответил, попробуй позже")
        return
    if d.get("status") != "success":
        await m.answer("Данных по этому IP нет")
        return
    flags = []
    if d.get("proxy"):
        flags.append("прокси/VPN")
    if d.get("hosting"):
        flags.append("хостинг/дата-центр")
    await m.answer(
        f"🌐 {ip}\n"
        f"🌍 {d.get('country')}, {d.get('regionName')}, {d.get('city')}\n"
        f"📡 Провайдер: {d.get('isp')}\n"
        f"🏢 Организация: {d.get('org') or '-'}\n"
        f"🔢 AS: {d.get('as')}\n"
        f"🕒 Часовой пояс: {d.get('timezone')}\n"
        f"⚠️ Метки: {', '.join(flags) if flags else 'нет'}"
    )
@dp.message(Command("domain"))
async def domain(m: Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await m.answer("Напиши так: /domain example.com")
        return
    name = parts[1].strip().lower()
    name = name.replace("https://", "").replace("http://", "").split("/")[0]
    if not re.fullmatch(r"([a-z0-9-]+\.)+[a-z]{2,}", name):
        await m.answer("Не похоже на домен. Пример: example.com")
        return
    tm = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession() as s:
        async def dns(t):
            try:
                async with s.get("https://dns.google/resolve",
                                 params={"name": name, "type": t}, timeout=tm) as r:
                    d = await r.json(content_type=None)
                return [a["data"] for a in d.get("Answer", [])]
            except Exception:
                return []
        async def rdap():
            try:
                async with s.get(f"https://rdap.org/domain/{name}", timeout=tm) as r:
                    if r.status != 200:
                        return {}
                    return await r.json(content_type=None)
            except Exception:
                return {}
        a, mx, ns, txt, info = await asyncio.gather(
            dns("A"), dns("MX"), dns("NS"), dns("TXT"), rdap()
        )
    ev = {e.get("eventAction"): (e.get("eventDate") or "")[:10] for e in info.get("events", [])}
    lines = [f"🌐 {name}"]
    lines.append(f"📅 Создан: {ev.get('registration', '-')}")
    lines.append(f"⏳ Истекает: {ev.get('expiration', '-')}")
    lines.append(f"🔄 Изменён: {ev.get('last changed', '-')}")
    lines.append(f"📍 A: {', '.join(a) if a else '-'}")
    lines.append(f"📬 MX: {', '.join(mx) if mx else '-'}")
    lines.append(f"🧭 NS: {', '.join(ns) if ns else '-'}")
    if txt:
        lines.append("📝 TXT: " + " | ".join(t[:80] for t in txt[:3]))
    await m.answer("\n".join(lines))
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
