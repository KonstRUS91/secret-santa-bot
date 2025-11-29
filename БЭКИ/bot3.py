import logging
import os
import random
import string
import asyncio
import sqlite3
import datetime
from aiogram import Bot, Dispatcher, Router, types
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не задана!")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

# === FSM ===
class Form(StatesGroup):
    waiting_for_game_code = State()
    waiting_for_wish = State()
    waiting_for_santa_message = State()
    waiting_for_ward_message = State()

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def get_main_kb_static():
    """Статическая клавиатура без проверки создателя (для ошибок)"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆕 Создать игру"), KeyboardButton(text="🚪 Присоединиться")],
            [KeyboardButton(text="🎁 Мои пожелания"), KeyboardButton(text="📜 Пожелания подопечного")],
            [KeyboardButton(text="🎅 Написать Санте"), KeyboardButton(text="👧 Написать подопечному")],
            [KeyboardButton(text="🚪 Покинуть игру")]
        ],
        resize_keyboard=True
    )

async def get_main_kb(user_id: int) -> ReplyKeyboardMarkup:
    conn = sqlite3.connect("santa.db")
    c = conn.cursor()
    c.execute("SELECT game_code FROM games WHERE creator_id = ?", (user_id,))
    game_row = c.fetchone()
    conn.close()

    keyboard = [
        [KeyboardButton(text="🆕 Создать игру"), KeyboardButton(text="🚪 Присоединиться")],
        [KeyboardButton(text="🎁 Мои пожелания"), KeyboardButton(text="📜 Пожелания подопечного")],
        [KeyboardButton(text="🎅 Написать Санте"), KeyboardButton(text="👧 Написать подопечному")],
        [KeyboardButton(text="🚪 Покинуть игру")]
    ]

    if game_row:
        game_code = game_row[0]
        conn = sqlite3.connect("santa.db")
        c = conn.cursor()
        c.execute("SELECT 1 FROM participants WHERE game_code = ? AND ward_of IS NOT NULL LIMIT 1", (game_code,))
        draw_done = c.fetchone() is not None
        conn.close()

        if not draw_done:
            keyboard.insert(1, [KeyboardButton(text="🎲 Жеребьёвка")])
        keyboard.insert(1, [KeyboardButton(text="👥 Список участников")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_gift_confirmation_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data="gift_bought"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="gift_cancel")
        ]
    ])

# === ОБРАБОТЧИКИ ===

@router.message(Command("start"))
async def cmd_start(message: Message):
    from database import init_db
    init_db()
    await message.answer("🎄 Добро пожаловать в игру «Тайный Санта»!", reply_markup=await get_main_kb(message.from_user.id))

@router.message(lambda m: m.text == "🆕 Создать игру")
async def create_game_handler(message: Message):
    from database import create_game
    game_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    create_game(game_code, message.from_user.id)
    await message.answer(
        f"✅ Игра создана! Код для участников:\n\n<b>{game_code}</b>\n\nПоделись этим кодом, чтобы друзья присоединились!",
        parse_mode="HTML",
        reply_markup=await get_main_kb(message.from_user.id)
    )

@router.message(lambda m: m.text == "🚪 Присоединиться")
async def join_game_start(message: Message, state: FSMContext):
    await message.answer("Введите код игры:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True
    ))
    await state.set_state(Form.waiting_for_game_code)

@router.message(Form.waiting_for_game_code)
async def join_game_process(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=await get_main_kb(message.from_user.id))
        return
    from database import join_game
    success = join_game(
        user_id=message.from_user.id,
        username=message.from_user.username or str(message.from_user.id),
        full_name=message.from_user.full_name,
        game_code=message.text.strip().upper()
    )
    if success:
        await message.answer(
            f"✅ Вы присоединились к игре!\n\nТеперь в меню нажмите кнопку\n\n🎁<b>Мои пожелания</b>\n\nи задайте свои пожелания.", parse_mode="HTML",
            reply_markup=await get_main_kb(message.from_user.id)
        )
    else:
        await message.answer("❌ Вы уже участвуете или код неверный.", reply_markup=await get_main_kb(message.from_user.id))
    await state.clear()

@router.message(lambda m: m.text == "🎁 Мои пожелания")
async def wish_start(message: Message, state: FSMContext):
    await message.answer("Напишите, что бы вы хотели получить в подарок:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True
    ))
    await state.set_state(Form.waiting_for_wish)

@router.message(Form.waiting_for_wish)
async def wish_save(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=await get_main_kb(message.from_user.id))
        return
    from database import set_wish
    set_wish(message.from_user.id, message.text)
    await message.answer("✅ Пожелания сохранены!", reply_markup=await get_main_kb(message.from_user.id))
    await state.clear()

@router.message(lambda m: m.text == "📜 Пожелания подопечного")
async def show_ward_wish(message: Message):
    conn = sqlite3.connect("santa.db")
    c = conn.cursor()
    c.execute("""
        SELECT p.ward_of, p2.full_name, p2.username, p2.wish
        FROM participants p
        LEFT JOIN participants p2 ON p.ward_of = p2.user_id
        WHERE p.user_id = ?
    """, (message.from_user.id,))
    row = c.fetchone()
    conn.close()

    if not row or not row[0]:
        await message.answer("❌ Жеребьёвка ещё не проведена.", reply_markup=await get_main_kb(message.from_user.id))
        return

    ward_id, full_name, username, wish = row
    name_display = full_name or f"ID{ward_id}"
    if username:
        name_display += f" (@{username})"
    wish_text = wish.strip() if wish and wish.strip() else "не указал(а) пожеланий."

    await message.answer(
        f"🧸 Ваш подопечный: <b>{name_display}</b>\n\n"
        f"Хочет:\n<i>{wish_text}</i>\n\n"
        f"Вы уже купили подарок?",
        parse_mode="HTML",
        reply_markup=get_gift_confirmation_kb()
    )

@router.callback_query(lambda c: c.data == "gift_bought")
async def handle_gift_bought(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    conn = sqlite3.connect("santa.db")
    c = conn.cursor()
    c.execute("SELECT ward_of FROM participants WHERE user_id = ?", (user_id,))
    ward_row = c.fetchone()
    conn.close()

    if not ward_row or not ward_row[0]:
        await callback.answer("Ошибка: подопечный не найден.", show_alert=True)
        return

    ward_id = ward_row[0]
    try:
        await bot.send_message(
            ward_id,
            "🎅 <b>Хорошие новости!</b>\n\n"
            "Ваш Санта уже купил для вас подарок! 🎁\n"
            "Осталось дождаться вручения!",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Не удалось отправить подопечному {ward_id}: {e}")

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Отлично! Подопечный получил уведомление.", reply_markup=await get_main_kb(user_id))

@router.callback_query(lambda c: c.data == "gift_cancel")
async def handle_gift_cancel(callback: types.CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("↩️ Возврат в главное меню.", reply_markup=await get_main_kb(callback.from_user.id))

@router.message(lambda m: m.text == "🎅 Написать Санте")
async def to_santa_start(message: Message, state: FSMContext):
    from database import get_santa_id
    santa_id = get_santa_id(message.from_user.id)
    if not santa_id:
        await message.answer("❌ Жеребьёвка ещё не проведена.", reply_markup=await get_main_kb(message.from_user.id))
        return
    await message.answer("Напишите сообщение своему Санте:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True
    ))
    await state.set_state(Form.waiting_for_santa_message)

@router.message(Form.waiting_for_santa_message)
async def to_santa_send(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=await get_main_kb(message.from_user.id))
        return
    from database import get_santa_id
    santa_id = get_santa_id(message.from_user.id)
    if santa_id:
        try:
            await bot.send_message(santa_id, f"📬 Ваш подопечный прислал сообщение:\n\n<i>{message.text}</i>", parse_mode="HTML")
            await message.answer("✅ Сообщение отправлено Санте!")
        except:
            await message.answer("⚠️ Не удалось отправить сообщение.")
    await state.clear()
    await message.answer("Возврат в меню.", reply_markup=await get_main_kb(message.from_user.id))

@router.message(lambda m: m.text == "👧 Написать подопечному")
async def to_ward_start(message: Message, state: FSMContext):
    from database import get_ward_id
    ward_id = get_ward_id(message.from_user.id)
    if not ward_id:
        await message.answer("❌ Жеребьёвка ещё не проведена.", reply_markup=await get_main_kb(message.from_user.id))
        return
    await message.answer("Напишите сообщение своему подопечному:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True
    ))
    await state.set_state(Form.waiting_for_ward_message)

@router.message(Form.waiting_for_ward_message)
async def to_ward_send(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=await get_main_kb(message.from_user.id))
        return
    from database import get_ward_id
    ward_id = get_ward_id(message.from_user.id)
    if ward_id:
        try:
            await bot.send_message(ward_id, f"🎅 Ваш Санта прислал сообщение:\n\n<i>{message.text}</i>", parse_mode="HTML")
            await message.answer("✅ Сообщение отправлено подопечному!")
        except:
            await message.answer("⚠️ Не удалось отправить сообщение.")
    await state.clear()
    await message.answer("Возврат в меню.", reply_markup=await get_main_kb(message.from_user.id))

@router.message(lambda m: m.text == "🚪 Покинуть игру")
async def leave_game_button(message: Message):
    conn = sqlite3.connect("santa.db")
    c = conn.cursor()
    c.execute("DELETE FROM participants WHERE user_id = ?", (message.from_user.id,))
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    if changed:
        await message.answer("✅ Вы покинули игру.", reply_markup=get_main_kb_static())
    else:
        await message.answer("❌ Вы не участвуете ни в одной игре.", reply_markup=get_main_kb_static())

@router.message(Command("leave"))
async def leave_game_command(message: Message):
    conn = sqlite3.connect("santa.db")
    c = conn.cursor()
    c.execute("DELETE FROM participants WHERE user_id = ?", (message.from_user.id,))
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    if changed:
        await message.answer("✅ Вы покинули игру.", reply_markup=get_main_kb_static())
    else:
        await message.answer("❌ Вы не участвуете ни в одной игре.", reply_markup=get_main_kb_static())

@router.message(lambda m: m.text == "👥 Список участников")
async def show_participants(message: Message):
    conn = sqlite3.connect("santa.db")
    c = conn.cursor()
    c.execute("SELECT game_code FROM games WHERE creator_id = ?", (message.from_user.id,))
    game_row = c.fetchone()
    if not game_row:
        await message.answer("❌ Эта функция доступна только создателю игры.")
        return
    game_code = game_row[0]
    c.execute("""
        SELECT full_name, username, wish
        FROM participants
        WHERE game_code = ?
        ORDER BY full_name
    """, (game_code,))
    participants = c.fetchall()
    conn.close()
    if not participants:
        await message.answer("📭 В игре пока нет участников.")
        return
    text = f"📋 Участники игры <b>{game_code}</b>:\n\n"
    for full_name, username, wish in participants:
        name = full_name or "Без имени"
        if username:
            name += f" (@{username})"
        wish_text = wish.strip() if wish and wish.strip() else "— не указаны"
        text += f"• {name}\n  🎁 {wish_text}\n\n"
    if len(text) > 4096:
        text = text[:4093] + "..."
    await message.answer(text, parse_mode="HTML")

@router.message(lambda m: m.text == "🎲 Жеребьёвка")
async def draw_via_button(message: Message):
    from database import assign_pairs
    user_id = message.from_user.id
    conn = sqlite3.connect("santa.db")
    c = conn.cursor()
    c.execute("SELECT game_code FROM games WHERE creator_id = ?", (user_id,))
    game_row = c.fetchone()
    if not game_row:
        await message.answer("❌ Только создатель может запустить жеребьёвку.")
        return
    game_code = game_row[0]
    c.execute("SELECT 1 FROM participants WHERE game_code = ? AND ward_of IS NOT NULL LIMIT 1", (game_code,))
    if c.fetchone():
        await message.answer("✅ Жеребьёвка уже проведена!")
        return
    success = assign_pairs(game_code)
    if not success:
        await message.answer("❌ Недостаточно участников (минимум 3).")
        return
    c.execute("SELECT user_id, ward_of FROM participants WHERE game_code = ?", (game_code,))
    assignments = c.fetchall()
    conn.close()
    success_count = 0
    for santa_id, ward_id in assignments:
        if not ward_id:
            continue
        conn2 = sqlite3.connect("santa.db")
        c2 = conn2.cursor()
        c2.execute("SELECT full_name, username, wish FROM participants WHERE user_id = ?", (ward_id,))
        ward_data = c2.fetchone()
        conn2.close()
        if ward_data:
            full_name, username, wish = ward_data
            name_display = full_name or f"ID{ward_id}"
            if username:
                name_display += f" (@{username})"
            wish_text = wish.strip() if wish and wish.strip() else "не указал(а) пожеланий."
            try:
                await bot.send_message(
                    santa_id,
                    f"🎅 <b>Жеребьёвка завершена!</b>\n\n"
                    f"Ваш подопечный: <b>{name_display}</b>\n\n"
                    f"🎁 Пожелания:\n<i>{wish_text}</i>",
                    parse_mode="HTML"
                )
                success_count += 1
            except Exception as e:
                logging.error(f"Ошибка отправки Санте {santa_id}: {e}")
    await message.answer(f"✅ Жеребьёвка проведена! Уведомления отправлены {success_count} участникам.")

@router.message(Command("draw"))
async def draw_handler(message: Message):
    await draw_via_button(message)

# === ЗАПУСК ===
dp.include_router(router)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())