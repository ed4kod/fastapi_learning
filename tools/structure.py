# запуск из корня:  python tools\structure.py

import os
import sys

EXCLUDE = {'venv', '.venv', '__pycache__', '.idea', '.git', 'tools'}

def tree(dir_path, prefix=""):
    entries = [e for e in os.listdir(dir_path) if e not in EXCLUDE]
    for i, name in enumerate(entries):
        path = os.path.join(dir_path, name)
        pointer = '└── ' if i == len(entries) - 1 else '├── '
        print(prefix + pointer + name)
        if os.path.isdir(path):
            extension = "    " if pointer == '└── ' else "│   "
            tree(path, prefix + extension)

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    print(f"{os.path.basename(os.path.abspath(path))}/")
    tree(path)

