from aiogram import Router, types
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from html import escape
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

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


class DoneStates(StatesGroup):
    waiting_for_task_id = State()


class DeleteStates(StatesGroup):
    waiting_for_task_id = State()


@router.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "👋 Привет, я твой бот-помощник с задачами!\n\nВыбери действие ниже:",
        reply_markup=main_menu
    )


@router.message(lambda m: m.text == "📋 Список задач")
async def handle_task_list_button(message: types.Message):
    await list_tasks_handler(message)


@router.message(lambda m: m.text == "➕ Добавить задачу")
async def handle_add_task_button(message: types.Message, state: FSMContext):
    await message.answer("📝 Введите название новой задачи:")
    await state.set_state(AddTaskStates.waiting_for_task_title)


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


@router.message(Command("list_tasks"))
async def list_tasks_handler(message: types.Message):
    db = SessionLocal()
    try:
        tasks = crud.get_tasks(db, user_id=message.from_user.id)
        if not tasks:
            await message.answer("📭 Список задач пуст.")
        else:
            for task in tasks:
                status = "✅" if task.done else "❌"
                text = f"{task.id}. {task.title} [{status}]"

                if task.done:
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="❌ Не выполнена", callback_data=f"undone_{task.id}"),
                            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{task.id}")
                        ]
                    ])
                else:
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="✅ Выполнить", callback_data=f"done_{task.id}"),
                            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{task.id}")
                        ]
                    ])

                await message.answer(text, reply_markup=keyboard)
    finally:
        db.close()


@router.callback_query(lambda c: c.data.startswith("done_"))
async def inline_done_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    db = SessionLocal()
    try:
        task = crud.mark_task_done(db, task_id)
        if task:
            status = "✅"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="❌ Не выполнена", callback_data=f"undone_{task.id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{task.id}")
            ]])
            await callback.message.edit_text(f"{task.id}. {task.title} [{status}]", reply_markup=keyboard)
            await callback.answer("Задача отмечена выполненной!")
        else:
            await callback.answer("Задача не найдена.", show_alert=True)
    finally:
        db.close()


@router.callback_query(lambda c: c.data.startswith("undone_"))
async def inline_undone_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    db = SessionLocal()
    try:
        task = crud.mark_task_undone(db, task_id)
        if task:
            status = "❌"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Выполнить", callback_data=f"done_{task.id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{task.id}")
            ]])
            await callback.message.edit_text(f"{task.id}. {task.title} [{status}]", reply_markup=keyboard)
            await callback.answer("Задача отмечена как невыполненной!")
        else:
            await callback.answer("Задача не найдена.", show_alert=True)
    finally:
        db.close()


@router.message(DoneStates.waiting_for_task_id)
async def process_done_task_id(message: types.Message, state: FSMContext):
    task_id = message.text.strip()
    if not task_id.isdigit():
        await message.answer("❗ ID задачи должен быть числом. Попробуйте снова:")
        return

    await process_done_task(message, int(task_id))
    await state.clear()


async def process_done_task(message: types.Message, task_id: int):
    db = SessionLocal()
    try:
        task = crud.mark_task_done(db, task_id)
        if task:
            await message.answer(f"✅ Задача #{task_id} отмечена как выполненная.")
        else:
            await message.answer(f"❗ Задача с id {task_id} не найдена.")
    finally:
        db.close()


@router.message(Command("delete"))
async def delete_command_handler(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)

    if len(parts) > 1:
        task_id = parts[1].strip()
        if task_id.isdigit():
            await process_delete_task(message, int(task_id))
            return

    await message.answer("🔢 Введите ID задачи для удаления:")
    await state.set_state(DeleteStates.waiting_for_task_id)


@router.message(DeleteStates.waiting_for_task_id)
async def process_delete_task_id(message: types.Message, state: FSMContext):
    task_id = message.text.strip()
    if not task_id.isdigit():
        await message.answer("❗ ID задачи должен быть числом. Попробуйте снова:")
        return

    await process_delete_task(message, int(task_id))
    await state.clear()


async def process_delete_task(message: types.Message, task_id: int):
    db = SessionLocal()
    try:
        task = crud.delete_task(db, task_id)
        if task:
            await message.answer(f"🗑 Задача #{task_id} удалена.")
        else:
            await message.answer(f"❗ Задача с id {task_id} не найдена.")
    finally:
        db.close()


@router.callback_query(lambda c: c.data.startswith("delete_"))
async def inline_delete_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    await process_delete_task(callback.message, task_id)
    await callback.answer("Задача удалена!")


@router.callback_query(lambda c: c.data == "create_task")
async def inline_create_task_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 Введите название новой задачи:")
    await state.set_state(AddTaskStates.waiting_for_task_title)
    await callback.answer()


@router.callback_query(lambda c: c.data == "list_tasks")
async def inline_list_tasks(callback: types.CallbackQuery):
    fake_message = callback.message
    await list_tasks_handler(fake_message)
    await callback.answer()
