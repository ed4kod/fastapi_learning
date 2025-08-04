import asyncio
from datetime import datetime
from aiogram import Router, types
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from html import escape
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import logging
from app import crud, schemas
from app.config import SessionLocal
from aiogram.exceptions import TelegramBadRequest
from time import time

router = Router()

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Список задач")],
        [KeyboardButton(text="➕ Добавить задачу")]
    ],
    resize_keyboard=True
)


class PrivateChatFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        return message.chat.type == "private"


router.message.filter(PrivateChatFilter())


class AddTaskStates(StatesGroup):
    waiting_for_task_title = State()


class EditTaskStates(StatesGroup):
    waiting_for_new_title = State()


@router.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    sent = await message.answer(
        "👋 Привет, я твой бот-помощник с задачами!",
        reply_markup=main_menu
    )

    # Удаляем команду /start от пользователя
    try:
        await message.delete()
    except Exception:
        pass

    await state.update_data(start_message_id=sent.message_id)


@router.message(lambda m: m.text == "📋 Список задач")
async def handle_task_list_button(message: types.Message, state: FSMContext):
    data = await state.get_data()

    # Удаляем приветственное сообщение
    start_msg_id = data.get("start_message_id")
    if start_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=start_msg_id)
        except Exception:
            pass
        await state.update_data(start_message_id=None)

    # Удаляем сообщение пользователя "📋 Список задач"
    try:
        await message.delete()
    except Exception:
        pass

    await cleanup_repeated_message(message, state)
    await send_tasks_list(message, state)


@router.message(lambda m: m.text == "➕ Добавить задачу")
async def handle_add_task_button(message: types.Message, state: FSMContext):
    prompt_msg = await message.answer("📝 Введите название новой задачи:")
    await state.set_state(AddTaskStates.waiting_for_task_title)
    await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.message(AddTaskStates.waiting_for_task_title)
async def process_task_title(message: types.Message, state: FSMContext):
    task_title = escape(message.text.strip())
    if not task_title:
        await message.answer("❗ Название задачи не может быть пустым.")
        return

    data = await state.get_data()
    prompt_msg_id = data.get("prompt_message_id")

    db = SessionLocal()
    try:
        new_task = crud.create_task(db, schemas.TaskCreate(title=task_title, user_id=message.from_user.id))
    finally:
        db.close()

    await state.clear()

    # Удаляем приглашение к вводу
    if prompt_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception:
            pass

    # Удаляем сообщение пользователя с текстом задачи
    try:
        await message.delete()
    except Exception:
        pass

    # Показываем временное уведомление
    notify = await message.bot.send_message(
        chat_id=message.chat.id,
        text=f"✅ Задача добавлена: {new_task.id}",
        reply_markup=main_menu
    )
    await asyncio.sleep(2)
    try:
        await notify.delete()
    except Exception:
        pass


def generate_task_keyboard(task):
    buttons = [
        InlineKeyboardButton(
            text="✅" if not task.done else "❌",
            callback_data=f"{'done' if not task.done else 'undone'}_{task.id}"
        ),
        InlineKeyboardButton(text="✏", callback_data=f"edit_{task.id}"),
        InlineKeyboardButton(text="🗑", callback_data=f"delete_{task.id}")
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def generate_task_text(task, username=""):
    status_icon = "✅" if task.done else "❌"
    text = f"{status_icon} {escape(task.title)}"
    if task.done and task.done_by:
        text += f"\n👤 Выполнил: {task.done_by}"
    return text


async def send_tasks_list(message: types.Message | types.CallbackQuery, state: FSMContext = None):
    db = SessionLocal()
    try:
        if isinstance(message, types.Message):
            user_id = message.chat.id
            bot = message.bot
            user_obj = message.from_user
        else:  # CallbackQuery
            user_id = message.message.chat.id
            bot = message.bot
            user_obj = message.from_user

        tasks = crud.get_tasks(db, user_id=user_id)

        if state:
            data = await state.get_data()
            old_msgs = data.get("last_messages", [])
            old_chat_id = data.get("last_chat_id", None)
            if old_msgs and old_chat_id == user_id:
                await delete_old_task_messages(bot, old_chat_id, old_msgs)

        sent_ids = []
        today = datetime.now().strftime('%d.%m.%Y')
        header_text = f"📋 Список задач на {today}"
        refresh_markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔄", callback_data="list_tasks")]]
        )
        header = await bot.send_message(chat_id=user_id, text=header_text, reply_markup=refresh_markup)
        sent_ids.append(header.message_id)

        if not tasks:
            empty_msg = await bot.send_message(chat_id=user_id, text="📭 Список задач пуст.")
            sent_ids.append(empty_msg.message_id)
        else:
            for task in tasks:
                username = user_obj.username if user_obj and hasattr(user_obj, "username") else ""
                task_text = generate_task_text(task, username)
                keyboard = generate_task_keyboard(task)
                task_msg = await bot.send_message(chat_id=user_id, text=task_text, reply_markup=keyboard)
                sent_ids.append(task_msg.message_id)

        if state:
            await state.update_data(last_messages=sent_ids, last_chat_id=user_id)

    finally:
        db.close()


@router.message(Command("list_tasks"))
async def list_tasks_handler(message: types.Message, state: FSMContext):
    await send_tasks_list(message, state)


@router.callback_query(lambda c: c.data == "list_tasks")
async def inline_list_tasks(callback: types.CallbackQuery, state: FSMContext):
    try:
        await prevent_callback_spam(callback, state)
    except Exception:
        return

    data = await state.get_data()
    old_msgs = data.get("last_messages", [])
    old_chat_id = data.get("last_chat_id", None)
    if old_msgs and old_chat_id == callback.message.chat.id:
        await delete_old_task_messages(callback.bot, old_chat_id, old_msgs)

    await send_tasks_list(callback, state)
    await callback.answer()


async def update_task_message(callback: types.CallbackQuery, task_id: int):
    db = SessionLocal()
    try:
        task = crud.get_task(db, task_id)
        if task:
            new_text = generate_task_text(task)
            new_markup = generate_task_keyboard(task)
            await callback.message.edit_text(new_text, reply_markup=new_markup)
    finally:
        db.close()


@router.callback_query(lambda c: c.data.startswith("done_"))
async def inline_done_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[1])
    db = SessionLocal()
    try:
        user = callback.from_user
        username = f" @{user.username}" if user.username else f" {user.full_name}"
        crud.mark_task_done(db, task_id, done_by=username)
    finally:
        db.close()
    await update_task_message(callback, task_id)
    await callback.answer("Задача отмечена выполненной!")


@router.callback_query(lambda c: c.data.startswith("undone_"))
async def inline_undone_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[1])
    db = SessionLocal()
    try:
        crud.mark_task_undone(db, task_id)
    finally:
        db.close()
    await update_task_message(callback, task_id)
    await callback.answer("Задача отмечена как невыполненная!")


@router.callback_query(lambda c: c.data.startswith("delete_"))
async def inline_delete_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[1])
    db = SessionLocal()
    try:
        crud.delete_task(db, task_id)
    finally:
        db.close()
    await callback.message.delete()
    await callback.answer("Задача удалена!")
    await send_tasks_list(callback, state)


@router.callback_query(lambda c: c.data.startswith("edit_"))
async def edit_task_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[1])
    await state.set_state(EditTaskStates.waiting_for_new_title)

    # Отправляем сообщение-приглашение к вводу
    prompt_msg = await callback.message.answer("✏ Введите новый текст задачи:")

    # Сохраняем ID обоих сообщений
    await state.update_data(
        task_id=task_id,
        message_id=callback.message.message_id,  # Сообщение с задачей
        prompt_message_id=prompt_msg.message_id  # Сообщение "✏ Введите новый текст"
    )

    await callback.answer()


@router.message(EditTaskStates.waiting_for_new_title)
async def process_edit_task(message: types.Message, state: FSMContext):
    new_title = escape(message.text.strip())
    data = await state.get_data()
    task_id = data.get("task_id")
    message_id = data.get("message_id")
    prompt_message_id = data.get("prompt_message_id")
    chat_id = message.chat.id

    if not new_title:
        await message.answer("❗ Название задачи не может быть пустым.")
        return

    db = SessionLocal()
    try:
        crud.update_task(db, task_id, schemas.TaskUpdate(title=new_title))
        task = crud.get_task(db, task_id)
    finally:
        db.close()

    await state.clear()

    new_text = generate_task_text(task)
    new_markup = generate_task_keyboard(task)

    # Обновляем задачу
    if message_id:
        try:
            await message.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=new_text,
                                                reply_markup=new_markup)
        except TelegramBadRequest:
            await message.answer("⚠ Не удалось обновить сообщение задачи.")

    # Удаляем сообщение пользователя (введённый текст) и приглашение к вводу
    await message.delete()
    if prompt_message_id:
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=prompt_message_id)
        except Exception:
            pass


@router.message(Command("add_task"))
async def add_task_handler(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        task_title = escape(parts[1].strip())
        if not task_title:
            await message.answer("❗ Название задачи не может быть пустым.")
            return

        db = SessionLocal()
        try:
            new_task = crud.create_task(db, schemas.TaskCreate(title=task_title, user_id=message.from_user.id))
            await message.answer(f"✅ Задача добавлена: {new_task.id}")
        finally:
            db.close()
    else:
        await message.answer("📝 Пожалуйста, введи название задачи:")
        await state.set_state(AddTaskStates.waiting_for_task_title)


async def delete_old_task_messages(bot, chat_id: int, message_ids: list[int]):
    for msg_id in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logging.warning(f"Не удалось удалить сообщение {msg_id} в чате {chat_id}: {e}")


async def cleanup_repeated_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    last_text = data.get("last_text")
    last_msg_id = data.get("last_msg_id")
    last_time = data.get("last_time", 0)
    now = time()

    if last_text == message.text and now - last_time < 3:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_msg_id)
        except Exception:
            pass

    await state.update_data(
        last_text=message.text,
        last_msg_id=message.message_id,
        last_time=now
    )


async def prevent_callback_spam(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_cb_data = data.get("last_cb_data")
    last_cb_time = data.get("last_cb_time", 0)
    now = time()

    if last_cb_data == callback.data and now - last_cb_time < 3:
        await callback.answer("⏳ Подожди немного...")
        raise Exception("Spam prevented")

    await state.update_data(
        last_cb_data=callback.data,
        last_cb_time=now
    )
