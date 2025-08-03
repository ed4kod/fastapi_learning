# ToDoList API

### Простое API для управления задачами.

## Tech Stack:

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/fastapi-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/sqlalchemy-136791?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![Alembic](https://img.shields.io/badge/alembic-4D76A3?style=for-the-badge&logo=alembic&logoColor=white)
![SQLite](https://img.shields.io/badge/sqlite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Uvicorn](https://img.shields.io/badge/uvicorn-405DE6?style=for-the-badge&logo=uvicorn&logoColor=white)

## Установка и запуск

1. Клонировать репозиторий:
   ```bash
   git clone https://github.com/ed4kod/todolist_api.git
   ```
2. Создать и активировать виртуальное окружение:
   ```bash
   python -m venv .venv
   # если на Windows, то:
   .venv\Scripts\activate
   # если на Linux, то:
   source .venv/bin/activate
   ```
3. Установить зависимости:
   ```bash
   pip install -r requirements.txt
   ```
4. Подготовьте секретный файл с токенами:
   ```bash
   python tools/get_env.py
   ```
5. Применить миграции базы данных:
   ```bash
   alembic upgrade head
   ```
6. Запустить сервер:
   ```bash
   uvicorn app.main:app --reload
   ```
7. Перейдите по сслыке, чтобы увидеть эндпоинты:
   ```bash
   # либо через Swagger UI:
   http://127.0.0.1:8000/docs
   # либо через ReDoc:
   http://127.0.0.1:8000/redoc
   ```

7. Если хотите увидеть структуру проекта, то запустите из корня:
   ```bash
   # получить структуру проекта
   python tools\app_structure.py
   # получить структуру базы данных
   python tools\db_structure.py
   ```

