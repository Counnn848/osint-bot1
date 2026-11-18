import json
from datetime import datetime
from aiogram import BaseMiddleware, F
from aiogram.types import (InlineKeyboardMarkup, InlineKeyboardButton,
                           CallbackQuery, FSInputFile, BotCommand)
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

SITES = {
    "GitHub": "https://github.com/{}",
    "GitLab": "https://gitlab.com/{}",
    "Dev.to": "https://dev.to/{}",
    "Medium": "https://medium.com/@{}",
    "Keybase": "https://keybase.io/{}",
    "Replit": "https://replit.com/@{}",
    "Codeforces": "https://codeforces.com/profile/{}",
    "Chess.com": "https://www.chess.com/member/{}",
    "Lichess": "https://lichess.org/@/{}",
    "Last.fm": "https://www.last.fm/user/{}",
    "SoundCloud": "https://soundcloud.com/{}",
    "YouTube": "https://www.youtube.com/@{}",
    "Vimeo": "https://vimeo.com/{}",
    "Pinterest": "https://www.pinterest.com/{}/",
    "Behance": "https://www.behance.net/{}",
    "Dribbble": "https://dribbble.com/{}",
    "About.me": "https://about.me/{}",
    "Linktree": "https://linktr.ee/{}",
    "Gravatar": "https://gravatar.com/{}",
    "Pastebin": "https://pastebin.com/u/{}",
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
@dp.message(Command("sub"))
async def sub(m: Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await m.answer("Напиши так: /sub example.com")
        return
    name = parts[1].strip().lower()
    name = name.replace("https://", "").replace("http://", "").split("/")[0]
    if not re.fullmatch(r"([a-z0-9-]+\.)+[a-z]{2,}", name):
        await m.answer("Не похоже на домен. Пример: example.com")
        return
    await m.answer("Ищу, это может занять до 30 секунд...")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://crt.sh/",
                             params={"q": f"%.{name}", "output": "json"},
                             timeout=aiohttp.ClientTimeout(total=40)) as r:
                if r.status != 200:
                    await m.answer("crt.sh сейчас не отвечает, попробуй позже")
                    return
                data = await r.json(content_type=None)
    except Exception:
        await m.answer("crt.sh не ответил, попробуй позже")
        return
    subs = set()
    for row in data:
        for n in row.get("name_value", "").split("\n"):
            n = n.strip().lower().lstrip("*.")
            if n.endswith(name):
                subs.add(n)
    subs.discard(name)
    if not subs:
        await m.answer("Поддоменов не найдено")
        return
    lst = sorted(subs)
    shown = lst[:80]
    text = f"🔎 {name}: найдено {len(lst)}\n\n" + "\n".join(shown)
    if len(lst) > len(shown):
        text += f"\n\n...и ещё {len(lst) - len(shown)}"
    await m.answer(text[:4000])
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data.json")

TOOLS = {
    "nick": ("🔎 Ник", "/nick torvalds"),
    "phone": ("📱 Телефон", "/phone +79161234567"),
    "ip": ("🌐 IP", "/ip 8.8.8.8"),
    "domain": ("🧭 Домен", "/domain github.com"),
    "sub": ("🌿 Поддомены", "/sub github.com"),
}

HELP_TEXT = (
    "Команды:\n\n"
    "/nick ник — поиск ника на сайтах\n"
    "/phone номер — оператор и регион\n"
    "/ip адрес — страна, город, провайдер\n"
    "/domain домен — DNS и даты регистрации\n"
    "/sub домен — поддомены\n"
    "/profile — твой профиль\n"
    "/menu — главное меню"
)

def load():
    try:
        with open(DATA, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save(d):
    try:
        with open(DATA, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass

USERS = load()

def touch(user, cmd=None):
    uid = str(user.id)
    u = USERS.setdefault(uid, {"since": datetime.now().strftime("%d.%m.%Y"),
                               "total": 0, "cmds": {}})
    if cmd:
        u["total"] += 1
        u["cmds"][cmd] = u["cmds"].get(cmd, 0) + 1
    save(USERS)
    return u

class Stats(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            if event.from_user and event.text and event.text.startswith("/"):
                cmd = event.text.split()[0][1:].split("@")[0].lower()
                if cmd in TOOLS:
                    touch(event.from_user, cmd)
                elif cmd in ("start", "menu", "help", "profile"):
                    touch(event.from_user)
        except Exception:
            pass
        return await handler(event, data)

dp.message.outer_middleware(Stats())

def menu_kb():
    b = lambda k: InlineKeyboardButton(text=TOOLS[k][0], callback_data="t:" + k)
    return InlineKeyboardMarkup(inline_keyboard=[
        [b("nick"), b("phone")],
        [b("ip"), b("domain")],
        [b("sub")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="❔ Помощь", callback_data="help")],
    ])

@dp.message(Command("start", "menu"))
async def start(m: Message):
    await m.answer_photo(FSInputFile(os.path.join(BASE, "menu.png")),
                         caption="Выбери инструмент 👇", reply_markup=menu_kb())

@dp.message(Command("help"))
async def help_cmd(m: Message):
    await m.answer(HELP_TEXT, reply_markup=menu_kb())

async def send_profile(msg: Message, user):
    u = touch(user)
    top = sorted(u["cmds"].items(), key=lambda x: -x[1])
    lines = "\n".join(f"  {c}: {n}" for c, n in top) or "  пока пусто"
    text = (f"👤 {user.full_name}\n🆔 {user.id}\n📅 С нами с: {u['since']}\n"
            f"📊 Запросов: {u['total']}\n\nПо командам:\n{lines}")
    await msg.answer_photo(FSInputFile(os.path.join(BASE, "profile.png")),
                           caption=text[:1000])

@dp.message(Command("profile"))
async def profile_cmd(m: Message):
    await send_profile(m, m.from_user)

@dp.callback_query(F.data.startswith("t:"))
async def tool_btn(c: CallbackQuery):
    title, example = TOOLS[c.data[2:]]
    await c.message.answer(f"{title}\nОтправь команду в таком виде:\n{example}")
    await c.answer()

@dp.callback_query(F.data == "profile")
async def profile_btn(c: CallbackQuery):
    await send_profile(c.message, c.from_user)
    await c.answer()

@dp.callback_query(F.data == "help")
async def help_btn(c: CallbackQuery):
    await c.message.answer(HELP_TEXT)
    await c.answer()
# ---------- меню: новые пункты ----------
TOOLS["archive"] = ("🕰 Архив", "/archive github.com")
HELP_TEXT += "\n/archive домен — старые версии сайта\n📷 EXIF — отправь фото как файл"

def menu_kb():
    b = lambda k: InlineKeyboardButton(text=TOOLS[k][0], callback_data="t:" + k)
    return InlineKeyboardMarkup(inline_keyboard=[
        [b("nick"), b("phone")],
        [b("ip"), b("domain")],
        [b("sub"), b("archive")],
        [InlineKeyboardButton(text="📷 EXIF", callback_data="exif_hint")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="❔ Помощь", callback_data="help")],
    ])

@dp.callback_query(F.data == "exif_hint")
async def exif_hint(c: CallbackQuery):
    await c.message.answer("📷 Отправь фото КАК ФАЙЛ: скрепка → Файл (не «Галерея»). "
                           "Иначе Telegram сотрёт метаданные.")
    await c.answer()

async def set_cmds2(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="menu", description="Главное меню"),
        BotCommand(command="help", description="Список команд"),
        BotCommand(command="profile", description="Мой профиль"),
        BotCommand(command="nick", description="Поиск ника"),
        BotCommand(command="phone", description="Данные по номеру"),
        BotCommand(command="ip", description="Данные по IP"),
        BotCommand(command="domain", description="Данные по домену"),
        BotCommand(command="sub", description="Поддомены"),
        BotCommand(command="archive", description="Старые версии сайта"),
    ])

dp.startup.register(set_cmds2)

# ---------- EXIF ----------
def _dms(v, ref):
    d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
    return -d if ref in ("S", "W") else d

def read_exif(data: bytes):
    im = Image.open(io.BytesIO(data))
    ex = im.getexif()
    tags = {}
    for src in (ex, ex.get_ifd(0x8769)):
        for k, v in src.items():
            tags[ExifTags.TAGS.get(k, str(k))] = v
    gps = ex.get_ifd(0x8825)
    pos = None
    if gps.get(2) and gps.get(4):
        pos = (_dms(gps[2], gps.get(1, "N")), _dms(gps[4], gps.get(3, "E")))
    return im, tags, pos

@dp.message(F.photo)
async def photo_warn(m: Message):
    await m.answer("Telegram стирает метаданные из обычных фото 😕\n"
                   "Отправь снимок как ФАЙЛ: скрепка → Файл.")

@dp.message(F.document)
async def exif_doc(m: Message):
    d = m.document
    if (d.file_size or 0) > 20 * 1024 * 1024:
        await m.answer("Файл больше 20 МБ, бот такой не скачает")
        return
    if not (d.mime_type or "").startswith("image/"):
        await m.answer("Нужна картинка (лучше JPEG), отправленная как файл")
        return
    touch(m.from_user, "exif")
    try:
        buf = await bot.download(d)
        im, tags, pos = read_exif(buf.read())
    except Exception:
        await m.answer("Не смог прочитать файл. Подойдёт JPEG (HEIC пока не поддерживается)")
        return
    want = [("Make", "Производитель"), ("Model", "Модель"), ("LensModel", "Объектив"),
            ("Software", "Программа"), ("DateTimeOriginal", "Снято"),
            ("DateTime", "Изменено"), ("ExposureTime", "Выдержка"),
            ("FNumber", "Диафрагма"), ("ISOSpeedRatings", "ISO")]
    lines = [f"🖼 {im.format}, {im.size[0]}x{im.size[1]}"]
    for key, label in want:
        v = tags.get(key)
        if v not in (None, ""):
            lines.append(f"{label}: {str(v)[:80]}")
    if pos:
        lines.append(f"📍 GPS: {pos[0]:.5f}, {pos[1]:.5f}\n"
                     f"https://maps.google.com/?q={pos[0]:.6f},{pos[1]:.6f}")
    if len(lines) == 1:
        lines.append("Метаданных нет: их стёрли или фото из мессенджера/соцсети")
    await m.answer("\n".join(lines))

# ---------- Web Archive ----------
@dp.message(Command("archive"))
async def archive(m: Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await m.answer("Напиши так: /archive example.com")
        return
    name = parts[1].strip().lower()
    name = name.replace("https://", "").replace("http://", "").split("/")[0]
    if not re.fullmatch(r"([a-z0-9-]+\.)+[a-z]{2,}", name):
        await m.answer("Не похоже на домен. Пример: example.com")
        return
    await m.answer("Ищу в Web Archive, до 30 секунд...")

    async def cdx(s, limit):
        async with s.get("https://web.archive.org/cdx/search/cdx",
                         params={"url": name, "output": "json", "fl": "timestamp",
                                 "limit": limit, "filter": "statuscode:200"},
                         timeout=aiohttp.ClientTimeout(total=30)) as r:
            text = await r.text()
        if not text.strip():
            return None
        rows = json.loads(text)
        return rows[1][0] if len(rows) > 1 else None

    try:
        async with aiohttp.ClientSession() as s:
            first, last = await asyncio.gather(cdx(s, 1), cdx(s, -1))
    except Exception:
        await m.answer("Web Archive не ответил, попробуй позже")
        return
    if not first:
        await m.answer("Снимков этого сайта нет")
        return
    fmt = lambda ts: f"{ts[6:8]}.{ts[4:6]}.{ts[:4]}"
    await m.answer(
        f"🕰 {name}\n\n"
        f"📌 Первый снимок: {fmt(first)}\nhttps://web.archive.org/web/{first}/{name}\n\n"
        f"🆕 Последний: {fmt(last or first)}\nhttps://web.archive.org/web/{last or first}/{name}\n\n"
        f"📚 Все снимки:\nhttps://web.archive.org/web/*/{name}"
  )
async def set_cmds(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="menu", description="Главное меню"),
        BotCommand(command="help", description="Список команд"),
        BotCommand(command="profile", description="Мой профиль"),
        BotCommand(command="nick", description="Поиск ника"),
        BotCommand(command="phone", description="Данные по номеру"),
        BotCommand(command="ip", description="Данные по IP"),
        BotCommand(command="domain", description="Данные по домену"),
        BotCommand(command="sub", description="Поддомены"),
    ])

dp.startup.register(set_cmds)
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
