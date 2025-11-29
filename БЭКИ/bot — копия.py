import logging
import os
import random
import string
import asyncio
from aiogram import Bot, Dispatcher, Router, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from database import *

# === Настройки ===
BOT_TOKEN = os.getenv("BOT_TOKEN")  # обязательно задай в переменных окружения!
if not BOT_TOKEN:
    raise ValueError("Установите переменную окружения BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

# === FSM состояния ===
class Form(StatesGroup):
    waiting_for_game_code = State()
    waiting_for_wish = State()
    waiting_for_santa_message = State()
    waiting_for_ward_message = State()

# === Клавиатуры ===
def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
           [KeyboardButton(text="🆕 Создать игру"), KeyboardButton(text="🚪 Присоединиться")],
           [KeyboardButton(text="🎁 Мои пожелания"), KeyboardButton(text="📜 Пожелания подопечного")],
           [KeyboardButton(text="🎅 Написать Санте"), KeyboardButton(text="👧 Написать подопечному")],
           [KeyboardButton(text="🚪 Покинуть игру")]
        ],
        resize_keyboard=True
    )

def cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )

# === Обработчики ===
@router.message(Command("start"))
async def cmd_start(message: Message):
    init_db()
    await message.answer("🎄 Добро пожаловать в игру «Тайный Санта»!", reply_markup=main_kb())

@router.message(lambda m: m.text == "🆕 Создать игру")
async def create_game_handler(message: Message):
    game_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    create_game(game_code, message.from_user.id)
    await message.answer(f"✅ Игра создана! Код для участников:\n\n<b>{game_code}</b>\n\nПоделись этим кодом, чтобы друзья присоединились!", parse_mode="HTML")

@router.message(lambda m: m.text == "🚪 Присоединиться")
async def join_game_start(message: Message, state: FSMContext):
    await message.answer("Введите код игры:", reply_markup=cancel_kb())
    await state.set_state(Form.waiting_for_game_code)

@router.message(Form.waiting_for_game_code)
async def join_game_process(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_kb())
        return
    game_code = message.text.strip().upper()
    success = join_game(
        user_id=message.from_user.id,
        username=message.from_user.username or str(message.from_user.id),
        full_name=message.from_user.full_name,
        game_code=game_code
    )
    if success:
        await message.answer(f"✅ Вы присоединились к игре <b>{game_code}</b>!\n\nТеперь задайте свои пожелания.", parse_mode="HTML", reply_markup=main_kb())
    else:
        await message.answer("❌ Вы уже участвуете в игре или код неверный.")
    await state.clear()

@router.message(lambda m: m.text == "🎁 Мои пожелания")
async def wish_start(message: Message, state: FSMContext):
    await message.answer("Напишите, что бы вы хотели получить в подарок:", reply_markup=cancel_kb())
    await state.set_state(Form.waiting_for_wish)

@router.message(lambda m: m.text == "📜 Пожелания подопечного")
async def show_ward_wish(message: Message):
    conn = sqlite3.connect("santa.db")
    c = conn.cursor()
    
    # Получаем ID и данные подопечного
    c.execute("""
        SELECT p.ward_of, p2.full_name, p2.username, p2.wish
        FROM participants p
        LEFT JOIN participants p2 ON p.ward_of = p2.user_id
        WHERE p.user_id = ?
    """, (message.from_user.id,))
    
    row = c.fetchone()
    conn.close()
    
    if not row or not row[0]:
        # Проверим, участвует ли пользователь вообще
        conn2 = sqlite3.connect("santa.db")
        c2 = conn2.cursor()
        c2.execute("SELECT 1 FROM participants WHERE user_id = ?", (message.from_user.id,))
        in_game = c2.fetchone()
        conn2.close()
        if not in_game:
            await message.answer("❌ Вы не участвуете в игре.")
        else:
            await message.answer("❌ Жеребьёвка ещё не проведена.")
        return

    ward_id, full_name, username, wish = row
    name_display = full_name or f"ID{ward_id}"
    if username:
        name_display += f" (@{username})"

    wish_text = wish.strip() if wish and wish.strip() else "не указал(а) пожеланий."

    await message.answer(
        f"🧸 Ваш подопечный: <b>{name_display}</b>\n\n"
        f"Хочет:\n<i>{wish_text}</i>",
        parse_mode="HTML"
    )

@router.message(Form.waiting_for_wish)
async def wish_save(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_kb())
        return
    set_wish(message.from_user.id, message.text)
    await message.answer("✅ Пожелания сохранены!", reply_markup=main_kb())
    await state.clear()

@router.message(lambda m: m.text == "🎅 Написать Санте")
async def to_santa_start(message: Message, state: FSMContext):
    santa_id = get_santa_id(message.from_user.id)
    if not santa_id:
        await message.answer("❌ Жеребьёвка ещё не проведена или вы не участвуете в игре.")
        return
    await message.answer("Напишите сообщение своему Санте (он получит его анонимно):", reply_markup=cancel_kb())
    await state.set_state(Form.waiting_for_santa_message)

@router.message(Form.waiting_for_santa_message)
async def to_santa_send(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_kb())
        return
    santa_id = get_santa_id(message.from_user.id)
    if santa_id:
        try:
            await bot.send_message(santa_id, f"📬 Ваш подопечный прислал сообщение:\n\n<i>{message.text}</i>", parse_mode="HTML")
            await message.answer("✅ Сообщение отправлено Санте!")
        except:
            await message.answer("⚠️ Не удалось отправить сообщение (возможно, Санта заблокировал бота).")
    await state.clear()
    await message.answer("Возврат в меню.", reply_markup=main_kb())

@router.message(lambda m: m.text == "👧 Написать подопечному")
async def to_ward_start(message: Message, state: FSMContext):
    ward_id = get_ward_id(message.from_user.id)
    if not ward_id:
        # Проверим, может, жеребьёвка не запущена?
        game_code = get_game_code_by_user(message.from_user.id)
        if not game_code:
            await message.answer("❌ Вы не участвуете в игре.")
            return
        if not is_draw_done(game_code):
            if is_creator(message.from_user.id, game_code):
                await message.answer(f"🎅 Жеребьёвка ещё не запущена!\n\nОтправьте команду <b>/draw</b>, чтобы начать распределение.", parse_mode="HTML")
            else:
                await message.answer("❌ Жеребьёвка ещё не проведена.")
            return
        else:
            await message.answer("❌ Ошибка: вы не назначенник ни для кого.")
            return
    await message.answer("Напишите сообщение своему подопечному (он получит его анонимно):", reply_markup=cancel_kb())
    await state.set_state(Form.waiting_for_ward_message)

@router.message(Form.waiting_for_ward_message)
async def to_ward_send(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_kb())
        return
    ward_id = get_ward_id(message.from_user.id)
    if ward_id:
        try:
            await bot.send_message(ward_id, f"🎅 Ваш Санта прислал сообщение:\n\n<i>{message.text}</i>", parse_mode="HTML")
            await message.answer("✅ Сообщение отправлено подопечному!")
        except:
            await message.answer("⚠️ Не удалось отправить сообщение (возможно, подопечный заблокировал бота).")
    await state.clear()
    await message.answer("Возврат в меню.", reply_markup=main_kb())

# === Команда для запуска жеребьёвки (только создатель) ===
@router.message(Command("draw"))
async def draw_handler(message: Message):
    game_code = get_game_code_by_user(message.from_user.id)
    if not game_code:
        await message.answer("❌ Вы не участвуете ни в одной игре.")
        return
    if not is_creator(message.from_user.id, game_code):
        await message.answer("❌ Только создатель игры может запустить жеребьёвку.")
        return
    if is_draw_done(game_code):
        await message.answer("✅ Жеребьёвка уже проведена!")
        return
    success = assign_pairs(game_code)
    if success:
        await message.answer("✅ Жеребьёвка завершена! Теперь вы можете писать своему Санте и подопечному.")
        # Опционально: уведомить всех участников
        for user_id in get_participants(game_code):
            try:
                await bot.send_message(user_id, "🎁 Жеребьёвка завершена! Нажмите «🎅 Написать Санте» или «👧 Написать подопечному».")
            except:
                pass
    else:
        await message.answer("❌ Недостаточно участников (минимум 3) или техническая ошибка.")

# === Выход из игры ===
@router.message(Command("leave"))
async def leave_game_command(message: Message):
    conn = sqlite3.connect("santa.db")
    c = conn.cursor()
    c.execute("DELETE FROM participants WHERE user_id = ?", (message.from_user.id,))
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    if changed:
        await message.answer("✅ Вы покинули игру. Теперь вы можете присоединиться к другой.", reply_markup=main_kb())
    else:
        await message.answer("❌ Вы не участвуете ни в одной игре.", reply_markup=main_kb())

@router.message(lambda m: m.text == "🚪 Покинуть игру")
async def leave_game_button(message: Message):
    # Вызываем ту же логику, что и в команде /leave
    conn = sqlite3.connect("santa.db")
    c = conn.cursor()
    c.execute("DELETE FROM participants WHERE user_id = ?", (message.from_user.id,))
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    if changed:
        await message.answer("✅ Вы покинули игру.", reply_markup=main_kb())
    else:
        await message.answer("❌ Вы не участвуете ни в одной игре.", reply_markup=main_kb())
# === Запуск ===
dp.include_router(router)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())