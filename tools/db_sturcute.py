import sqlite3

def show_db_structure(db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Получаем список таблиц
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    print(f"📦 Таблицы в базе '{db_path}':\n")
    for (table_name,) in tables:
        print(f"🧱 Таблица: {table_name}")
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        for col in columns:
            col_id, name, col_type, notnull, default, pk = col
            print(f"   ├─ {name} ({col_type}){' PRIMARY KEY' if pk else ''}")
        print()

    conn.close()

# Пример использования:
if __name__ == "__main__":
    show_db_structure("app/todolist.db")  # путь к твоей базе
