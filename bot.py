import asyncio
import logging

from config import *

from aiogram import Dispatcher, Bot, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State

from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, \
    KeyboardButton, ChatType
from aiogram.utils import exceptions, executor
from sqlalchemy.future import select

import re

from config import TOKEN, ADMINS
from data.db_session import create_session, global_init
from data.user import User

bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
dp.middleware.setup(LoggingMiddleware())


regex = re.compile(r'([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+')

class Reg(StatesGroup):
    agreement = State()
    name = State()
    email = State()


class Main(StatesGroup):
    main = State()


async def safe_send_message(user_id: int, text: str) -> bool:
    """
    Safe messages sender
    :param user_id:
    :param text:
    :param keyboard_markup:
    :return:
    """
    try:
        await bot.send_message(chat_id=user_id, text=text)
    except exceptions.BotBlocked:
        logging.error(f"Target [ID:{user_id}]: blocked by user")
    except exceptions.ChatNotFound:
        logging.error(f"Target [ID:{user_id}]: invalid user ID")
    except exceptions.RetryAfter as e:
        logging.error(f"Target [ID:{user_id}]: Flood limit is exceeded. Sleep {e.timeout} seconds.")
        await asyncio.sleep(e.timeout)
        return await safe_send_message(user_id, text)  # Recursive call
    except exceptions.UserDeactivated:
        logging.error(f"Target [ID:{user_id}]: user is deactivated")
    except exceptions.TelegramAPIError:
        logging.exception(f"Target [ID:{user_id}]: failed")
    else:
        logging.info(f"Target [ID:{user_id}]: success")
        return True
    return False


@dp.message_handler(commands='get_id', chat_type=[ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL], state='*')
async def chat(message: types.Message):
    await message.answer("ID вашего чата: " + str(message.chat.id))


@dp.message_handler(commands='list', state='*', )
@dp.throttled(rate=5)
async def list_of_members(message: types.Message):
    if message.from_user.id in ADMINS:
        async with create_session() as sess:
            result = await sess.execute(select(User))
            users = result.scalars().all()
        msg = ''
        k = 1
        for user in users:
            msg += f"{k}. {user.name} - {user.email}"
            if user.username:
                msg += " - @" + user.username
            msg += "\n"
            k += 1
        await message.answer(text=msg)


@dp.message_handler(commands='mail', state='*')
@dp.throttled(rate=5)
async def mail(message: types.Message):
    if message.from_user.id in ADMINS:
        async with create_session() as sess:
            result = await sess.execute(select(User.user_id))
            users = result.scalars().all()
        msg = message.text[5:]
        for user in users:
            await safe_send_message(user, msg)
            await asyncio.sleep(0.1)


@dp.message_handler(commands='start', state='*')
@dp.throttled(rate=5)
async def start(message: types.Message):
    async with create_session() as sess:
        result = await sess.execute(select(User.user_id).where(User.user_id == message.from_user.id))
        user = result.scalars().first()
    if not user:
        msg = """Приветствую тебя , я Sberi, бот Воронежского Сбер Акселератора🐢. 
    
Я занимаюсь оповещением о наших мероприятиях, а также регистрацией участников.
❗️Обязательно проходи регистрацию , а иначе тебя не пустят на мероприятие❗️"""
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("Условия", url="telegra.ph"))
        keyboard.add(InlineKeyboardButton("Принять условия", callback_data="agree"))

        await Reg.agreement.set()
        await message.answer(msg, reply_markup=keyboard)
    else:
        msg = "Привет! Скоро тут появятся мероприятия"
        await message.answer(msg)


@dp.callback_query_handler(state=Reg.agreement)
async def agreement(query: types.CallbackQuery):
    if query.data == "agree":
        await query.message.delete()
        msg = "Введите свои имя и фамилию\n\nНапример: Иванов Иван"
        await Reg.name.set()
        await query.message.answer(msg)


@dp.message_handler(state=Reg.name)
async def name(message: types.Message, state: FSMContext):
    if len(message.text.split()) == 2:
        async with state.proxy() as data:
            data['name'] = message.text
        await message.answer("Введите свой email")
        await Reg.email.set()
    else:
        msg = "Неправильно введены данные"
        await message.answer(msg)


@dp.message_handler(state=Reg.email)
async def email(message: types.Message, state: FSMContext):
    if re.fullmatch(regex, message.text):
        async with state.proxy() as data:
            data['email'] = message.text
            async with create_session() as sess:
                user = User()
                user.user_id = message.from_user.id
                user.email = message.text
                try:
                    user.username = message.from_user.username
                except: pass
                user.name = data['name']
                sess.add(user)
                await sess.commit()

        msg_2 = f"НОВЫЙ УЧАСТНИК\n\n{user.name} - {user.email}"
        await bot.send_message(chat_id=CHANNEL, text=msg_2)

        msg = "Спасибо за регистрацию! Вам придет напоминание за день до мероприятия"
        await state.finish()
        await Main.main.set()
    else:
        msg = "Неправильно введен email"
    await message.answer(msg)


async def startup_(_):
    await global_init(user=DB_LOGIN, password=DB_PASSWORD,
                      host=DB_HOST, port=DB_PORT, dbname=DB_NAME)


async def shutdown(dispatcher: Dispatcher):
    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_shutdown=shutdown, on_startup=startup_)
