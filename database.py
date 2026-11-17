import aiosqlite
import math

DB_PATH = "billiard_bot.db"


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
        await db.commit()


async def get_or_create_user(telegram_id: int, username: str, full_name: str):
    """Получает пользователя или создаёт нового"""
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
    """Возвращает профиль пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT * FROM users WHERE telegram_id = ?',
            (telegram_id,)
        )
        return await cursor.fetchone()


async def get_top_players(limit: int = 10):
    """Возвращает топ игроков по рейтингу"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT * FROM users ORDER BY elo_rating DESC LIMIT ?',
            (limit,)
        )
        return await cursor.fetchall()


def calculate_elo(winner_elo: int, loser_elo: int, k_factor: int = 32):
    """Формула расчета ELO рейтинга"""
    expected_winner = 1 / (1 + math.pow(10, (loser_elo - winner_elo) / 400))
    expected_loser = 1 / (1 + math.pow(10, (winner_elo - loser_elo) / 400))

    new_winner_elo = round(winner_elo + k_factor * (1 - expected_winner))
    new_loser_elo = round(loser_elo + k_factor * (0 - expected_loser))
    return new_winner_elo, new_loser_elo


async def get_user_by_username(username: str):
    """Ищет пользователя по никнейму (без @)"""
    username = username.lstrip('@')
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT * FROM users WHERE username = ?', (username,))
        return await cursor.fetchone()


async def record_match(winner_id: int, loser_id: int):
    """
    Записывает результат матча и обновляет ELO обоих игроков.
    Возвращает: (success: bool, new_winner_elo: int|None, new_loser_elo: int|None)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT elo_rating, games_played, wins FROM users WHERE telegram_id = ?',
            (winner_id,)
        )
        winner_data = await cursor.fetchone()

        cursor = await db.execute(
            'SELECT elo_rating, games_played, wins FROM users WHERE telegram_id = ?',
            (loser_id,)
        )
        loser_data = await cursor.fetchone()

        if not winner_data or not loser_data:
            return False, None, None

        new_winner_elo, new_loser_elo = calculate_elo(winner_data[0], loser_data[0])

        await db.execute('''
            UPDATE users
            SET elo_rating = ?, games_played = games_played + 1, wins = wins + 1
            WHERE telegram_id = ?
        ''', (new_winner_elo, winner_id))

        await db.execute('''
            UPDATE users
            SET elo_rating = ?, games_played = games_played + 1
            WHERE telegram_id = ?
        ''', (new_loser_elo, loser_id))

        await db.commit()
        return True, new_winner_elo, new_loser_elo


async def get_all_users(limit=30):
    """Возвращает список игроков для выбора соперника"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT telegram_id, username, full_name, elo_rating FROM users '
            'ORDER BY elo_rating DESC LIMIT ?',
            (limit,)
        )
        return await cursor.fetchall()
