import os

def rename_env_file():
    try:
        os.rename('env.example', '.env')
        print("Файл успешно переименован из env.example в .env")
    except FileNotFoundError:
        print("Ошибка: файл env.example не найден в текущей директории")
    except Exception as e:
        print(f"Произошла ошибка: {e}")

if __name__ == "__main__":
    rename_env_file()