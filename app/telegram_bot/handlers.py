from aiogram import Router, types
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from html import escape

from app import crud, schemas
from app.config import SessionLocal

router = Router()


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
        "👋 Привет, я твой бот-помощник с задачами!\n\n📌 Доступные команды:\n"
        "/add_task - добавить задачу\n"
        "/list_tasks - список задач\n"
        "/done - отметить задачу выполненной\n"
        "/delete - удалить задачу"
    )


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
            new_task = crud.create_task(db, schemas.TaskCreate(title=task_title))
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
        new_task = crud.create_task(db, schemas.TaskCreate(title=task_title))
        await message.answer(f"✅ Задача добавлена: {new_task.id}")
    finally:
        db.close()

    await state.clear()


@router.message(Command("list_tasks"))
async def list_tasks_handler(message: types.Message):
    db = SessionLocal()
    try:
        tasks = crud.get_tasks(db)
        if not tasks:
            await message.answer("📭 Список задач пуст.")
            return

        response = "📋 Список задач:\n\n"
        for task in tasks:
            status = "✅" if task.done else "❌"
            response += f"{task.id}. {task.title} [{status}]\n"
        await message.answer(response)
    finally:
        db.close()


@router.message(Command("done"))
async def done_command_handler(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)

    if len(parts) > 1:
        task_id = parts[1].strip()
        if task_id.isdigit():
            await process_done_task(message, int(task_id))
            return

    await message.answer("🔢 Введите ID задачи для отметки как выполненной:")
    await state.set_state(DoneStates.waiting_for_task_id)


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