import aiosqlite
import math

DB_PATH = "billiard_bot.db"
MATCH_COOLDOWN_MINUTES = 30
CHALLENGE_RANGE = 10


async def init_db():
    """Создаёт таблицы в базе данных"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                elo_rating INTEGER DEFAULT 1000,
                games_played INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                winner_id INTEGER NOT NULL,
                loser_id INTEGER NOT NULL,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenger_id INTEGER NOT NULL,
                opponent_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS pending_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                winner_id INTEGER NOT NULL,
                loser_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.commit()


async def get_or_create_user(telegram_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT * FROM users WHERE telegram_id = ?',
            (telegram_id,)
        )
        user = await cursor.fetchone()
        if not user:
            await db.execute(
                'INSERT INTO users (telegram_id, username, full_name) VALUES (?, ?, ?)',
                (telegram_id, username, full_name)
            )
            await db.commit()
            cursor = await db.execute(
                'SELECT * FROM users WHERE telegram_id = ?',
                (telegram_id,)
            )
            user = await cursor.fetchone()
        return user


async def get_user_profile(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT * FROM users WHERE telegram_id = ?',
            (telegram_id,)
        )
        return await cursor.fetchone()


async def get_top_players(limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT * FROM users ORDER BY elo_rating DESC, telegram_id ASC LIMIT ?',
            (limit,)
        )
        return await cursor.fetchall()


def calculate_elo(winner_elo: int, loser_elo: int, k_factor: int = 32):
    expected_winner = 1 / (1 + math.pow(10, (loser_elo - winner_elo) / 400))
    expected_loser = 1 / (1 + math.pow(10, (winner_elo - loser_elo) / 400))
    new_winner_elo = round(winner_elo + k_factor * (1 - expected_winner))
    new_loser_elo = round(loser_elo + k_factor * (0 - expected_loser))
    return new_winner_elo, new_loser_elo


async def get_user_by_username(username: str):
    username = username.lstrip('@')
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT * FROM users WHERE username = ?', (username,))
        return await cursor.fetchone()


async def record_match(winner_id: int, loser_id: int):
    """Возвращает (success, data). data = (new_w_elo, new_l_elo) или строка ошибки."""
    if winner_id == loser_id:
        return False, "Нельзя записать матч с самим собой"

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            '''SELECT id FROM matches 
               WHERE ((winner_id = ? AND loser_id = ?) OR (winner_id = ? AND loser_id = ?))
               AND played_at > datetime('now', ?)''',
            (winner_id, loser_id, loser_id, winner_id, f'-{MATCH_COOLDOWN_MINUTES} minutes')
        )
        if await cursor.fetchone():
            return False, f"Матч между вами уже записан менее {MATCH_COOLDOWN_MINUTES} минут назад"

        cursor = await db.execute(
            'SELECT elo_rating FROM users WHERE telegram_id = ?', (winner_id,)
        )
        winner_data = await cursor.fetchone()
        cursor = await db.execute(
            'SELECT elo_rating FROM users WHERE telegram_id = ?', (loser_id,)
        )
        loser_data = await cursor.fetchone()
        if not winner_data or not loser_data:
            return False, "Один из игроков не найден в базе"

        new_winner_elo, new_loser_elo = calculate_elo(winner_data[0], loser_data[0])
        await db.execute(
            'UPDATE users SET elo_rating = ?, games_played = games_played + 1, wins = wins + 1 '
            'WHERE telegram_id = ?',
            (new_winner_elo, winner_id)
        )
        await db.execute(
            'UPDATE users SET elo_rating = ?, games_played = games_played + 1 '
            'WHERE telegram_id = ?',
            (new_loser_elo, loser_id)
        )
        await db.execute(
            'INSERT INTO matches (winner_id, loser_id) VALUES (?, ?)',
            (winner_id, loser_id)
        )
        await db.commit()
        return True, (new_winner_elo, new_loser_elo)


async def get_all_users(limit: int = 30):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT telegram_id, username, full_name, elo_rating FROM users '
            'ORDER BY elo_rating DESC, telegram_id ASC LIMIT ?',
            (limit,)
        )
        return await cursor.fetchall()


async def get_players_above(telegram_id: int, max_above: int = CHALLENGE_RANGE):
    """Список игроков выше telegram_id по рейтингу (не более max_above позиций).
    Формат: [(rank, tid, uname, fname, elo), ...] — от ближайшего к самому высокому."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT telegram_id, username, full_name, elo_rating FROM users '
            'ORDER BY elo_rating DESC, telegram_id ASC'
        )
        rows = await cursor.fetchall()
        user_index = None
        for i, row in enumerate(rows):
            if row[0] == telegram_id:
                user_index = i
                break
        if user_index is None or user_index == 0:
            return []
        start = max(0, user_index - max_above)
        result = []
        for i in range(user_index - 1, start - 1, -1):
            rank = i + 1
            tid, uname, fname, elo = rows[i]
            result.append((rank, tid, uname, fname, elo))
        return result


# === Функции для нового /top ===

async def get_total_players() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT COUNT(*) FROM users')
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_user_rank(telegram_id: int):
    """Позиция пользователя в рейтинге (1 = первый). None если не найден."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT elo_rating FROM users WHERE telegram_id = ?', (telegram_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        user_elo = row[0]
        cursor = await db.execute(
            '''SELECT COUNT(*) FROM users 
               WHERE elo_rating > ? 
               OR (elo_rating = ? AND telegram_id < ?)''',
            (user_elo, user_elo, telegram_id)
        )
        count_row = await cursor.fetchone()
        return count_row[0] + 1


async def get_players_upto(max_rank: int):
    """Список (rank, tid, uname, fname, elo) от 1-го до max_rank."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT telegram_id, username, full_name, elo_rating FROM users '
            'ORDER BY elo_rating DESC, telegram_id ASC LIMIT ?',
            (max_rank,)
        )
        rows = await cursor.fetchall()
        return [(i + 1, row[0], row[1], row[2], row[3]) for i, row in enumerate(rows)]


# === Challenges ===

async def create_challenge(challenger_id: int, opponent_id: int):
    if challenger_id == opponent_id:
        return False, "Нельзя вызвать самого себя"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM challenges WHERE status = 'pending' "
            "AND created_at < datetime('now', '-24 hours')"
        )
        cursor = await db.execute(
            "SELECT id FROM challenges WHERE challenger_id = ? AND opponent_id = ? "
            "AND status = 'pending'",
            (challenger_id, opponent_id)
        )
        if await cursor.fetchone():
            await db.commit()
            return False, "Ты уже отправил вызов этому игроку, жди ответа"
        await db.execute(
            'INSERT INTO challenges (challenger_id, opponent_id) VALUES (?, ?)',
            (challenger_id, opponent_id)
        )
        await db.commit()
        cursor = await db.execute('SELECT last_insert_rowid()')
        row = await cursor.fetchone()
        return True, row[0]


async def get_challenge(challenge_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT id, challenger_id, opponent_id, status FROM challenges WHERE id = ?',
            (challenge_id,)
        )
        return await cursor.fetchone()


async def update_challenge_status(challenge_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE challenges SET status = ? WHERE id = ?',
            (status, challenge_id)
        )
        await db.commit()


# === Pending results ===

async def create_pending_result(winner_id: int, loser_id: int):
    if winner_id == loser_id:
        return False, "Нельзя выбрать самого себя"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM pending_results WHERE created_at < datetime('now', '-24 hours')"
        )
        cursor = await db.execute(
            'SELECT id FROM pending_results WHERE winner_id = ? AND loser_id = ?',
            (winner_id, loser_id)
        )
        if await cursor.fetchone():
            await db.commit()
            return False, "Результат уже ожидает подтверждения от этого игрока"
        await db.execute(
            'INSERT INTO pending_results (winner_id, loser_id) VALUES (?, ?)',
            (winner_id, loser_id)
        )
        await db.commit()
        cursor = await db.execute('SELECT last_insert_rowid()')
        row = await cursor.fetchone()
        return True, row[0]


async def get_pending_result(pending_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT id, winner_id, loser_id FROM pending_results WHERE id = ?',
            (pending_id,)
        )
        return await cursor.fetchone()


async def delete_pending_result(pending_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM pending_results WHERE id = ?', (pending_id,))
        await db.commit()
