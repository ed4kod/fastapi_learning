from aiogram import Router, types
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from html import escape
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.markdown import hbold

from app import crud, schemas
from app.config import SessionLocal

router = Router()

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Список задач")],
        [KeyboardButton(text="➕ Добавить задачу")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие..."
)


class PrivateChatFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        return message.chat.type == "private"


router.message.filter(PrivateChatFilter())


class AddTaskStates(StatesGroup):
    waiting_for_task_title = State()


class EditTaskStates(StatesGroup):
    waiting_for_new_title = State()


class DeleteStates(StatesGroup):
    waiting_for_task_id = State()


@router.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "👋 Привет, я твой бот-помощник с задачами!\n\nВыбери действие ниже:",
        reply_markup=main_menu
    )


@router.message(lambda m: m.text == "📋 Список задач")
async def handle_task_list_button(message: types.Message, state: FSMContext):
    await list_tasks_handler(message, state)


@router.message(lambda m: m.text == "➕ Добавить задачу")
async def handle_add_task_button(message: types.Message, state: FSMContext):
    await message.answer("📝 Введите название новой задачи:")
    await state.set_state(AddTaskStates.waiting_for_task_title)


@router.message(AddTaskStates.waiting_for_task_title)
async def process_task_title(message: types.Message, state: FSMContext):
    task_title = escape(message.text.strip())
    if not task_title:
        await message.answer("❗ Название задачи не может быть пустым. Попробуй ещё раз.")
        return

    db = SessionLocal()
    try:
        new_task = crud.create_task(db, schemas.TaskCreate(title=task_title, user_id=message.from_user.id))
        await message.answer(f"✅ Задача добавлена: {new_task.id}")
    finally:
        db.close()

    await state.clear()


async def send_tasks_list(message: types.Message | types.CallbackQuery, state: FSMContext = None):
    db = SessionLocal()
    try:
        user_id = message.from_user.id if isinstance(message, types.Message) else message.message.chat.id
        username = message.from_user.username if isinstance(message, types.Message) else message.from_user.username
        tasks = crud.get_tasks(db, user_id=user_id)

        if state:
            data = await state.get_data()
            old_msgs: list[int] = data.get("last_messages", [])
            for msg_id in old_msgs:
                try:
                    await message.bot.delete_message(chat_id=user_id, message_id=msg_id)
                except Exception:
                    pass

        sent_ids = []

        # Заголовок + кнопка обновления
        refresh_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить список", callback_data="list_tasks")]
            ]
        )
        header = await message.bot.send_message(chat_id=user_id, text=f"👤 {username}", reply_markup=refresh_keyboard)
        sent_ids.append(header.message_id)

        if not tasks:
            msg = await message.bot.send_message(chat_id=user_id, text="📭 Список задач пуст.")
            sent_ids.append(msg.message_id)
        else:
            for task in tasks:
                status_icon = "✅" if task.done else "❌"
                text = f"{status_icon} {escape(task.title)}"
                buttons = InlineKeyboardMarkup(inline_keyboard=[[  # кнопки в одном ряду
                    InlineKeyboardButton(
                        text="✅" if not task.done else "❌",
                        callback_data=f"{'done' if not task.done else 'undone'}_{task.id}"
                    ),
                    InlineKeyboardButton(text="✏", callback_data=f"edit_{task.id}"),
                    InlineKeyboardButton(text="🗑", callback_data=f"delete_{task.id}")
                ]])
                msg = await message.bot.send_message(chat_id=user_id, text=text, reply_markup=buttons)
                sent_ids.append(msg.message_id)

        if state:
            await state.update_data(last_messages=sent_ids)

    finally:
        db.close()


@router.message(Command("list_tasks"))
async def list_tasks_handler(message: types.Message, state: FSMContext):
    await send_tasks_list(message, state)


@router.callback_query(lambda c: c.data == "list_tasks")
async def inline_list_tasks(callback: types.CallbackQuery, state: FSMContext):
    await send_tasks_list(callback, state)
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("done_"))
async def inline_done_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    db = SessionLocal()
    try:
        crud.mark_task_done(db, task_id)
    finally:
        db.close()
    await inline_list_tasks(callback)
    await callback.answer("Задача отмечена выполненной!")


@router.callback_query(lambda c: c.data.startswith("undone_"))
async def inline_undone_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    db = SessionLocal()
    try:
        crud.mark_task_undone(db, task_id)
    finally:
        db.close()
    await inline_list_tasks(callback)
    await callback.answer("Задача отмечена как невыполненная!")


@router.callback_query(lambda c: c.data.startswith("delete_"))
async def inline_delete_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    db = SessionLocal()
    try:
        crud.delete_task(db, task_id)
    finally:
        db.close()
    await inline_list_tasks(callback)
    await callback.answer("Задача удалена!")


@router.callback_query(lambda c: c.data.startswith("edit_"))
async def edit_task_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[1])
    await state.set_state(EditTaskStates.waiting_for_new_title)
    await state.update_data(task_id=task_id)
    await callback.message.answer("✏ Введите новый текст задачи:")
    await callback.answer()


@router.message(EditTaskStates.waiting_for_new_title)
async def process_edit_task(message: types.Message, state: FSMContext):
    new_title = escape(message.text.strip())
    data = await state.get_data()
    task_id = data.get("task_id")

    db = SessionLocal()
    try:
        crud.update_task(db, task_id, schemas.TaskUpdate(title=new_title))
    finally:
        db.close()

    await message.answer("✅ Задача обновлена!")
    await state.clear()


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


@router.callback_query(lambda c: c.data.startswith("toggle_"))
async def toggle_task_status(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    db = SessionLocal()
    try:
        task = crud.get_task(db, task_id)
        if task.done:
            crud.mark_task_undone(db, task_id)
        else:
            crud.mark_task_done(db, task_id)
    finally:
        db.close()
    await inline_list_tasks(callback)
    await callback.answer("Статус задачи изменён!")


@router.message(EditTaskStates.waiting_for_new_title)
async def process_edit_task(message: types.Message, state: FSMContext):
    new_title = escape(message.text.strip())
    data = await state.get_data()
    task_id = data.get("task_id")

    db = SessionLocal()
    try:
        crud.update_task(db, task_id, schemas.TaskUpdate(title=new_title))
    finally:
        db.close()

    # Удалить сообщение пользователя и предыдущее сообщение бота (если знаем msg_id)
    try:
        await message.delete()  # Удаляем текст задачи от пользователя
        await message.reply_to_message.delete()  # Удаляем сообщение "✏️ Введите новый текст задачи:"
    except Exception:
        pass  # Без паники, если вдруг одно из сообщений уже удалено

    await state.clear()

    # Обновить список задач
    await send_tasks_list(message)

    # Показать уведомление
    await message.answer("✅ Задача обновлена!", show_alert=False)
