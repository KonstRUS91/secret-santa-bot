import sqlite3
import random
from typing import Optional, List, Tuple

DB_PATH = "santa.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_code TEXT PRIMARY KEY,
            creator_id INTEGER NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            game_code TEXT NOT NULL,
            wish TEXT,
            santa_of INTEGER,  -- кому дарит (ward)
            ward_of INTEGER    -- от кого получает (santa)
        )
    """)
    conn.commit()
    conn.close()

def create_game(game_code: str, creator_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO games (game_code, creator_id) VALUES (?, ?)", (game_code, creator_id))
    conn.commit()
    conn.close()

def join_game(user_id: int, username: str, full_name: str, game_code: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM participants WHERE user_id = ?", (user_id,))
    if c.fetchone():
        conn.close()
        return False  # уже участвует
    c.execute("""
        INSERT OR IGNORE INTO participants 
        (user_id, username, full_name, game_code, wish, santa_of, ward_of)
        VALUES (?, ?, ?, ?, '', NULL, NULL)
    """, (user_id, username, full_name, game_code))
    conn.commit()
    conn.close()
    return True

def set_wish(user_id: int, wish: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE participants SET wish = ? WHERE user_id = ?", (wish, user_id))
    conn.commit()
    conn.close()

def get_wish(user_id: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT wish FROM participants WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def is_creator(user_id: int, game_code: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT creator_id FROM games WHERE game_code = ?", (game_code,))
    row = c.fetchone()
    conn.close()
    return row and row[0] == user_id

def get_participants(game_code: str) -> List[int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM participants WHERE game_code = ?", (game_code,))
    users = [r[0] for r in c.fetchall()]
    conn.close()
    return users

def assign_pairs(game_code: str) -> bool:
    users = get_participants(game_code)
    if len(users) < 3:
        return False

    shuffled = users[:]
    for _ in range(100):  # максимум 100 попыток
        random.shuffle(shuffled)
        # Проверяем, что никто не дарит себе
        if all(santa != ward for santa, ward in zip(users, shuffled)):
            break
    else:
        return False  # не удалось развести

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for santa, ward in zip(users, shuffled):
        c.execute("UPDATE participants SET ward_of = ? WHERE user_id = ?", (ward, santa))
        c.execute("UPDATE participants SET santa_of = ? WHERE user_id = ?", (santa, ward))
    conn.commit()
    conn.close()
    return True

def get_ward_id(user_id: int) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT ward_of FROM participants WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_santa_id(user_id: int) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT santa_of FROM participants WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_game_code_by_user(user_id: int) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT game_code FROM participants WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def is_draw_done(game_code: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM participants WHERE game_code = ? AND ward_of IS NOT NULL LIMIT 1", (game_code,))
    result = c.fetchone() is not None
    conn.close()
    return result