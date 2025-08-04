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
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError
from time import time
from typing import Optional

router = Router()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Константы
SPAM_PROTECTION_TIMEOUT = 1.0
MESSAGE_CLEANUP_TIMEOUT = 3.0
CONFIRMATION_DISPLAY_TIME = 1.5
MAX_TASK_TITLE_LENGTH = 200


class PrivateChatFilter(BaseFilter):
    """Фильтр для приватных чатов"""

    async def __call__(self, message: types.Message) -> bool:
        return message.chat.type == "private"


router.message.filter(PrivateChatFilter())


class AddTaskStates(StatesGroup):
    waiting_for_task_title = State()


class EditTaskStates(StatesGroup):
    waiting_for_new_title = State()


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Создает основную клавиатуру бота"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Список задач")],
            [KeyboardButton(text="➕ Добавить задачу")]
        ],
        resize_keyboard=True,
        persistent=True
    )
    return keyboard


def generate_task_keyboard(task) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру для задачи"""
    buttons = [
        InlineKeyboardButton(
            text="✅ Выполнено" if not task.done else "❌ Не выполнено",
            callback_data=f"{'done' if not task.done else 'undone'}_{task.id}"
        ),
        InlineKeyboardButton(
            text="✏️ Изменить",
            callback_data=f"edit_{task.id}"
        ),
        InlineKeyboardButton(
            text="🗑️ Удалить",
            callback_data=f"delete_{task.id}"
        )
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def generate_header_keyboard() -> InlineKeyboardMarkup:
    """Генерирует клавиатуру для заголовка списка задач"""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 Обновить", callback_data="list_tasks"),
        InlineKeyboardButton(text="➕ Добавить", callback_data="add_task")
    ]])


def generate_task_text(task, username: str = "") -> str:
    """Генерирует текст для отображения задачи"""
    status_icon = "✅" if task.done else "❌"
    text = f"{status_icon} <b>{escape(task.title)}</b>"

    if task.done and task.done_by:
        text += f"\n👤 <i>Выполнил:</i> {escape(task.done_by)}"

    return text


async def safe_delete_message(bot, chat_id: int, message_id: int) -> bool:
    """Безопасно удаляет сообщение"""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except TelegramAPIError as e:
        logger.debug(f"Не удалось удалить сообщение {message_id}: {e}")
        return False


async def safe_edit_message(bot, chat_id: int, message_id: int, text: str,
                            reply_markup: Optional[InlineKeyboardMarkup] = None) -> bool:
    """Безопасно редактирует сообщение"""
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return True  # Сообщение не изменилось - это нормально
        elif "message to edit not found" in str(e).lower():
            logger.warning(f"Сообщение {message_id} не найдено для редактирования")
            return False
        else:
            logger.error(f"Ошибка редактирования сообщения {message_id}: {e}")
            return False
    except TelegramAPIError as e:
        logger.error(f"API ошибка при редактировании сообщения {message_id}: {e}")
        return False


async def prevent_callback_spam(callback: types.CallbackQuery, state: FSMContext) -> bool:
    """Защита от спама callback'ов"""
    data = await state.get_data()
    last_cb_data = data.get("last_cb_data")
    last_cb_time = data.get("last_cb_time", 0)
    now = time()

    if last_cb_data == callback.data and now - last_cb_time < SPAM_PROTECTION_TIMEOUT:
        await callback.answer("⏳ Подождите немного перед следующим действием...", show_alert=False)
        return False

    await state.update_data(
        last_cb_data=callback.data,
        last_cb_time=now
    )
    return True


async def cleanup_state_messages(state: FSMContext, bot, chat_id: int, keys_to_cleanup: list[str]):
    """Очищает временные сообщения из состояния"""
    data = await state.get_data()
    updates = {}

    for key in keys_to_cleanup:
        message_id = data.get(key)
        if message_id:
            await safe_delete_message(bot, chat_id, message_id)
            updates[key] = None

    if updates:
        await state.update_data(**updates)


@router.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    """Обработчик команды /start"""
    # Очищаем состояние
    await state.clear()

    welcome_text = (
        "👋 <b>Добро пожаловать в менеджер задач!</b>\n\n"
        "📋 Здесь вы можете:\n"
        "• Создавать новые задачи\n"
        "• Отмечать задачи выполненными\n"
        "• Редактировать и удалять задачи\n\n"
        "Используйте кнопки ниже для управления:"
    )

    start_msg = await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

    await state.update_data(start_message_id=start_msg.message_id)


@router.message(lambda m: m.text == "📋 Список задач")
async def handle_task_list_button(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'Список задач'"""
    data = await state.get_data()

    # Удаляем приветственное сообщение
    start_msg_id = data.get("start_message_id")
    if start_msg_id:
        await safe_delete_message(message.bot, message.chat.id, start_msg_id)
        await state.update_data(start_message_id=None)

    # Удаляем сообщение пользователя
    await safe_delete_message(message.bot, message.chat.id, message.message_id)

    await send_tasks_list(message, state)


@router.message(lambda m: m.text == "➕ Добавить задачу")
async def handle_add_task_button(message: types.Message, state: FSMContext):
    """Обработчик кнопки 'Добавить задачу'"""
    # Очищаем предыдущие временные сообщения
    await cleanup_state_messages(
        state, message.bot, message.chat.id,
        ['prompt_message_id', 'confirmation_message_id']
    )

    # Удаляем сообщение пользователя
    await safe_delete_message(message.bot, message.chat.id, message.message_id)

    prompt_msg = await message.answer(
        "📝 <b>Введите название новой задачи:</b>\n"
        f"<i>Максимальная длина: {MAX_TASK_TITLE_LENGTH} символов</i>",
        parse_mode="HTML"
    )

    await state.set_state(AddTaskStates.waiting_for_task_title)
    await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.message(AddTaskStates.waiting_for_task_title)
async def process_task_title(message: types.Message, state: FSMContext):
    """Обработка ввода названия новой задачи"""
    task_title = message.text.strip() if message.text else ""

    # Валидация
    if not task_title:
        await message.answer("❗ <b>Название задачи не может быть пустым.</b>", parse_mode="HTML")
        return

    if len(task_title) > MAX_TASK_TITLE_LENGTH:
        await message.answer(
            f"❗ <b>Название задачи слишком длинное.</b>\n"
            f"Максимум: {MAX_TASK_TITLE_LENGTH} символов, у вас: {len(task_title)}",
            parse_mode="HTML"
        )
        return

    # Создаем задачу
    try:
        with SessionLocal() as db:
            new_task = crud.create_task(
                db,
                schemas.TaskCreate(title=task_title, user_id=message.from_user.id)
            )
            db.commit()
            # Сохраняем данные задачи до закрытия сессии
            task_id = new_task.id
            task_title_saved = new_task.title
    except Exception as e:
        logger.error(f"Ошибка создания задачи: {e}")
        await message.answer("❗ <b>Произошла ошибка при создании задачи.</b>", parse_mode="HTML")
        return

    # Очищаем состояние и временные сообщения
    await cleanup_state_messages(
        state, message.bot, message.chat.id,
        ['prompt_message_id']
    )
    await state.clear()

    # Удаляем сообщение пользователя
    await safe_delete_message(message.bot, message.chat.id, message.message_id)

    # Показываем подтверждение
    confirmation = await message.answer(
        f"✅ <b>Задача добавлена:</b> {escape(task_title_saved)}",
        parse_mode="HTML"
    )

    # Удаляем подтверждение через время
    await asyncio.sleep(CONFIRMATION_DISPLAY_TIME)
    await safe_delete_message(message.bot, message.chat.id, confirmation.message_id)

    # Обновляем список задач
    await send_tasks_list(message, state)


async def send_tasks_list(message: types.Message | types.CallbackQuery, state: FSMContext):
    """Отправляет/обновляет список задач"""
    if isinstance(message, types.Message):
        user_id = message.chat.id
        bot = message.bot
    else:  # CallbackQuery
        user_id = message.message.chat.id
        bot = message.bot

    # Получаем задачи из БД
    try:
        with SessionLocal() as db:
            tasks = crud.get_tasks(db, user_id=user_id)
            # Преобразуем в обычные объекты, чтобы избежать DetachedInstanceError
            tasks_data = []
            for task in tasks:
                tasks_data.append({
                    'id': task.id,
                    'title': task.title,
                    'done': task.done,
                    'done_by': task.done_by
                })
    except Exception as e:
        logger.error(f"Ошибка получения задач: {e}")
        error_msg = "❗ <b>Произошла ошибка при загрузке задач.</b>"
        if isinstance(message, types.Message):
            await message.answer(error_msg, parse_mode="HTML")
        else:
            await message.message.answer(error_msg, parse_mode="HTML")
        return

    # Создаем временные объекты задач
    class TempTask:
        def __init__(self, data):
            self.id = data['id']
            self.title = data['title']
            self.done = data['done']
            self.done_by = data['done_by']

    tasks = [TempTask(task_data) for task_data in tasks_data]

    # Получаем данные состояния
    data = await state.get_data()
    task_messages = data.get("task_messages", {})
    header_message_id = data.get("header_message_id")
    chat_id = user_id

    # Формируем текст заголовка
    date_str = datetime.now().strftime('%d.%m.%Y')
    task_count = len(tasks)

    if task_count == 0:
        header_text = f"📋 <b>Список задач на {date_str}</b>\n<i>Список пуст</i>"
    else:
        completed_count = sum(1 for task in tasks if task.done)
        header_text = (
            f"📋 <b>Список задач на {date_str}</b>\n"
            f"📊 Всего: {task_count} | Выполнено: {completed_count}"
        )

    header_markup = generate_header_keyboard()

    # Обработка заголовка
    if header_message_id:
        if not await safe_edit_message(bot, chat_id, header_message_id, header_text, header_markup):
            header_message_id = None

    if not header_message_id:
        try:
            header = await bot.send_message(
                chat_id=chat_id,
                text=header_text,
                reply_markup=header_markup,
                parse_mode="HTML"
            )
            header_message_id = header.message_id
            await state.update_data(header_message_id=header_message_id)
        except TelegramAPIError as e:
            logger.error(f"Ошибка отправки заголовка: {e}")
            return

    # Если задач нет, удаляем все сообщения задач и обновляем заголовок
    if not tasks:
        for task_id, msg_id in list(task_messages.items()):
            await safe_delete_message(bot, chat_id, msg_id)
            task_messages.pop(task_id, None)

        # Обновляем состояние с пустым списком сообщений задач
        await state.update_data(task_messages=task_messages)

        # Проверяем, нужно ли обновить заголовок для пустого списка
        empty_header_text = f"📋 <b>Список задач на {date_str}</b>\n<i>Список пуст</i>"

        if header_message_id:
            await safe_edit_message(bot, chat_id, header_message_id, empty_header_text, header_markup)
        else:
            try:
                header = await bot.send_message(
                    chat_id=chat_id,
                    text=empty_header_text,
                    reply_markup=header_markup,
                    parse_mode="HTML"
                )
                await state.update_data(header_message_id=header.message_id)
            except TelegramAPIError as e:
                logger.error(f"Ошибка отправки заголовка для пустого списка: {e}")

        return

    # Управление сообщениями задач
    current_task_ids = set(task.id for task in tasks)
    known_task_ids = set(task_messages.keys())

    # Удаляем сообщения для удаленных задач
    to_delete_ids = known_task_ids - current_task_ids
    for task_id in to_delete_ids:
        msg_id = task_messages.get(task_id)
        if msg_id:
            await safe_delete_message(bot, chat_id, msg_id)
            task_messages.pop(task_id, None)

    # Обновляем/создаем сообщения задач
    for task in tasks:
        task_id = task.id
        text = generate_task_text(task)
        markup = generate_task_keyboard(task)

        if task_id in task_messages:
            # Пытаемся обновить существующее сообщение
            if not await safe_edit_message(bot, chat_id, task_messages[task_id], text, markup):
                # Если не удалось обновить, создаем новое
                try:
                    msg = await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=markup,
                        parse_mode="HTML"
                    )
                    task_messages[task_id] = msg.message_id
                except TelegramAPIError as e:
                    logger.error(f"Ошибка отправки сообщения задачи: {e}")
        else:
            # Создаем новое сообщение
            try:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=markup,
                    parse_mode="HTML"
                )
                task_messages[task_id] = msg.message_id
            except TelegramAPIError as e:
                logger.error(f"Ошибка отправки нового сообщения задачи: {e}")

    # Сохраняем обновленные данные
    await state.update_data(task_messages=task_messages)


async def update_task_message(callback: types.CallbackQuery, task_id: int, state: FSMContext):
    """Обновляет сообщение конкретной задачи"""
    try:
        with SessionLocal() as db:
            task = crud.get_task(db, task_id)
            if not task:
                await callback.answer("❗ Задача не найдена!", show_alert=True)
                return

            # Сохраняем данные до закрытия сессии
            task_data = {
                'id': task.id,
                'title': task.title,
                'done': task.done,
                'done_by': task.done_by
            }

        # Создаем временный объект для генерации текста и клавиатуры
        class TempTask:
            def __init__(self, data):
                self.id = data['id']
                self.title = data['title']
                self.done = data['done']
                self.done_by = data['done_by']

        temp_task = TempTask(task_data)
        new_text = generate_task_text(temp_task)
        new_markup = generate_task_keyboard(temp_task)

        await safe_edit_message(
            callback.bot,
            callback.message.chat.id,
            callback.message.message_id,
            new_text,
            new_markup
        )
    except Exception as e:
        logger.error(f"Ошибка обновления сообщения задачи {task_id}: {e}")


@router.callback_query(lambda c: c.data == "list_tasks")
async def inline_list_tasks(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки обновления списка задач"""
    if not await prevent_callback_spam(callback, state):
        return

    await send_tasks_list(callback, state)
    await callback.answer("🔄 Список обновлен!")


@router.callback_query(lambda c: c.data.startswith("done_"))
async def inline_done_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик отметки задачи как выполненной"""
    if not await prevent_callback_spam(callback, state):
        return

    try:
        task_id = int(callback.data.split("_")[1])

        with SessionLocal() as db:
            user = callback.from_user
            username = f"@{user.username}" if user.username else user.full_name
            crud.mark_task_done(db, task_id, done_by=username)
            db.commit()

        await update_task_message(callback, task_id, state)
        await callback.answer("✅ Задача отмечена выполненной!")

    except (ValueError, IndexError):
        await callback.answer("❗ Неверный формат данных!", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка отметки задачи {task_id} как выполненной: {e}")
        await callback.answer("❗ Произошла ошибка!", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("undone_"))
async def inline_undone_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик отметки задачи как невыполненной"""
    if not await prevent_callback_spam(callback, state):
        return

    try:
        task_id = int(callback.data.split("_")[1])

        with SessionLocal() as db:
            crud.mark_task_undone(db, task_id)
            db.commit()

        await update_task_message(callback, task_id, state)
        await callback.answer("❌ Задача отмечена как невыполненная!")

    except (ValueError, IndexError):
        await callback.answer("❗ Неверный формат данных!", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка отметки задачи {task_id} как невыполненной: {e}")
        await callback.answer("❗ Произошла ошибка!", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("delete_"))
async def inline_delete_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик удаления задачи"""
    if not await prevent_callback_spam(callback, state):
        return

    try:
        task_id = int(callback.data.split("_")[1])

        with SessionLocal() as db:
            task = crud.get_task(db, task_id)
            if not task:
                await callback.answer("❗ Задача не найдена!", show_alert=True)
                return

            task_title = task.title
            crud.delete_task(db, task_id)
            db.commit()

        # Удаляем сообщение задачи
        data = await state.get_data()
        task_messages = data.get("task_messages", {})

        if task_id in task_messages:
            await safe_delete_message(
                callback.bot,
                callback.message.chat.id,
                task_messages[task_id]
            )
            task_messages.pop(task_id, None)
            await state.update_data(task_messages=task_messages)

        await callback.answer(f"🗑️ Задача удалена: {task_title}")

    except (ValueError, IndexError):
        await callback.answer("❗ Неверный формат данных!", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка удаления задачи {task_id}: {e}")
        await callback.answer("❗ Произошла ошибка!", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("edit_"))
async def edit_task_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик начала редактирования задачи"""
    if not await prevent_callback_spam(callback, state):
        return

    try:
        task_id = int(callback.data.split("_")[1])

        # Проверяем, что задача существует
        with SessionLocal() as db:
            task = crud.get_task(db, task_id)
            if not task:
                await callback.answer("❗ Задача не найдена!", show_alert=True)
                return

        await state.set_state(EditTaskStates.waiting_for_new_title)

        prompt_msg = await callback.message.answer(
            f"✏️ <b>Редактирование задачи</b>\n\n"
            f"<b>Текущее название:</b> {escape(task.title)}\n\n"
            f"📝 <b>Введите новое название:</b>\n"
            f"<i>Максимальная длина: {MAX_TASK_TITLE_LENGTH} символов</i>",
            parse_mode="HTML"
        )

        await state.update_data(
            task_id=task_id,
            message_id=callback.message.message_id,
            prompt_message_id=prompt_msg.message_id
        )

        await callback.answer("✏️ Начинаем редактирование...")

    except (ValueError, IndexError):
        await callback.answer("❗ Неверный формат данных!", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка начала редактирования задачи: {e}")
        await callback.answer("❗ Произошла ошибка!", show_alert=True)


@router.message(EditTaskStates.waiting_for_new_title)
async def process_edit_task(message: types.Message, state: FSMContext):
    """Обработка ввода нового названия задачи"""
    new_title = message.text.strip() if message.text else ""
    data = await state.get_data()
    task_id = data.get("task_id")
    message_id = data.get("message_id")

    # Валидация
    if not new_title:
        await message.answer("❗ <b>Название задачи не может быть пустым.</b>", parse_mode="HTML")
        return

    if len(new_title) > MAX_TASK_TITLE_LENGTH:
        await message.answer(
            f"❗ <b>Название задачи слишком длинное.</b>\n"
            f"Максимум: {MAX_TASK_TITLE_LENGTH} символов, у вас: {len(new_title)}",
            parse_mode="HTML"
        )
        return

    try:
        with SessionLocal() as db:
            task = crud.get_task(db, task_id)
            if not task:
                await message.answer("❗ <b>Задача не найдена!</b>", parse_mode="HTML")
                return

            crud.update_task(db, task_id, schemas.TaskUpdate(title=new_title))
            db.commit()
            updated_task = crud.get_task(db, task_id)

        # Очищаем состояние и временные сообщения
        await cleanup_state_messages(
            state, message.bot, message.chat.id,
            ['prompt_message_id']
        )
        await state.clear()

        # Обновляем сообщение задачи
        if message_id and updated_task:
            new_text = generate_task_text(updated_task)
            new_markup = generate_task_keyboard(updated_task)
            await safe_edit_message(
                message.bot, message.chat.id, message_id,
                new_text, new_markup
            )

        # Удаляем сообщение пользователя
        await safe_delete_message(message.bot, message.chat.id, message.message_id)

        # Показываем подтверждение
        confirmation = await message.answer(
            f"✅ <b>Задача обновлена:</b> {escape(new_title)}",
            parse_mode="HTML"
        )

        await asyncio.sleep(CONFIRMATION_DISPLAY_TIME)
        await safe_delete_message(message.bot, message.chat.id, confirmation.message_id)

    except Exception as e:
        logger.error(f"Ошибка обновления задачи {task_id}: {e}")
        await message.answer("❗ <b>Произошла ошибка при обновлении задачи.</b>", parse_mode="HTML")


@router.callback_query(lambda c: c.data == "add_task")
async def inline_add_task(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик инлайн-кнопки добавления задачи"""
    if not await prevent_callback_spam(callback, state):
        return

    # Очищаем предыдущие временные сообщения
    await cleanup_state_messages(
        state, callback.bot, callback.message.chat.id,
        ['prompt_message_id', 'confirmation_message_id']
    )

    prompt = await callback.message.answer(
        "📝 <b>Введите название новой задачи:</b>\n"
        f"<i>Максимальная длина: {MAX_TASK_TITLE_LENGTH} символов</i>",
        parse_mode="HTML"
    )

    await state.set_state(AddTaskStates.waiting_for_task_title)
    await state.update_data(prompt_message_id=prompt.message_id)
    await callback.answer("📝 Готов к вводу задачи!")


@router.message(Command("clear"))
async def clear_command(message: types.Message, state: FSMContext):
    """Команда для очистки всех сообщений бота"""
    data = await state.get_data()

    # Удаляем заголовок
    header_message_id = data.get("header_message_id")
    if header_message_id:
        await safe_delete_message(message.bot, message.chat.id, header_message_id)

    # Удаляем все сообщения задач
    task_messages = data.get("task_messages", {})
    for task_id, msg_id in task_messages.items():
        await safe_delete_message(message.bot, message.chat.id, msg_id)

    # Удаляем приветственное сообщение
    start_msg_id = data.get("start_message_id")
    if start_msg_id:
        await safe_delete_message(message.bot, message.chat.id, start_msg_id)

    # Очищаем состояние
    await state.clear()

    # Удаляем команду пользователя
    await safe_delete_message(message.bot, message.chat.id, message.message_id)

    # Отправляем новое приветствие
    await start_command(message, state)


@router.message(Command("refresh"))
async def refresh_command(message: types.Message, state: FSMContext):
    """Команда для принудительного обновления списка задач"""
    # Удаляем команду пользователя
    await safe_delete_message(message.bot, message.chat.id, message.message_id)

    # Очищаем старые данные о сообщениях
    data = await state.get_data()

    # Удаляем все старые сообщения
    header_message_id = data.get("header_message_id")
    if header_message_id:
        await safe_delete_message(message.bot, message.chat.id, header_message_id)

    task_messages = data.get("task_messages", {})
    for task_id, msg_id in task_messages.items():
        await safe_delete_message(message.bot, message.chat.id, msg_id)

    # Очищаем данные сообщений из состояния
    await state.update_data(
        header_message_id=None,
        task_messages={}
    )

    # Отправляем обновленный список
    await send_tasks_list(message, state)


@router.message(Command("list_tasks"))
async def list_tasks_handler(message: types.Message, state: FSMContext):
    """Обработчик команды /list_tasks"""
    await send_tasks_list(message, state)

    """Обработчик команды /add_task"""
    parts = message.text.split(maxsplit=1)

    if len(parts) > 1:
        task_title = parts[1].strip()

        if not task_title:
            await message.answer("❗ <b>Название задачи не может быть пустым.</b>", parse_mode="HTML")
            return

        if len(task_title) > MAX_TASK_TITLE_LENGTH:
            await message.answer(
                f"❗ <b>Название задачи слишком длинное.</b>\n"
                f"Максимум: {MAX_TASK_TITLE_LENGTH} символов, у вас: {len(task_title)}",
                parse_mode="HTML"
            )
            return

        try:
            with SessionLocal() as db:
                new_task = crud.create_task(
                    db,
                    schemas.TaskCreate(title=task_title, user_id=message.from_user.id)
                )
                db.commit()
                # Сохраняем данные до закрытия сессии
                task_id = new_task.id
                task_title_saved = new_task.title

            await message.answer(
                f"✅ <b>Задача добавлена:</b> {escape(task_title_saved)}\n"
                f"<i>ID: {task_id}</i>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка создания задачи через команду: {e}")
            await message.answer("❗ <b>Произошла ошибка при создании задачи.</b>", parse_mode="HTML")
    else:
        prompt_msg = await message.answer(
            "📝 <b>Введите название задачи:</b>\n"
            f"<i>Максимальная длина: {MAX_TASK_TITLE_LENGTH} символов</i>",
            parse_mode="HTML"
        )
        await state.set_state(AddTaskStates.waiting_for_task_title)
        await state.update_data(prompt_message_id=prompt_msg.message_id)


@router.message()
async def handle_unknown_message(message: types.Message, state: FSMContext):
    """Обработчик неизвестных сообщений"""
    current_state = await state.get_state()

    if current_state in [AddTaskStates.waiting_for_task_title, EditTaskStates.waiting_for_new_title]:
        return

    help_text = (
        "❓ <b>Неизвестная команда</b>\n\n"
        "📋 Доступные команды:\n"
        "• /start - Начать работу с ботом\n"
        "• /list_tasks - Показать список задач\n"
        "• /refresh - Обновить список задач\n"
        "• /clear - Очистить все сообщения\n\n"
        "🔘 Или используйте кнопки в меню:"
    )

    await message.answer(
        help_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )
