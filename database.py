import os
import math
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")
MATCH_COOLDOWN_MINUTES = 30
CHALLENGE_RANGE = 10
K_FACTOR = 30

if not DATABASE_URL:
    raise RuntimeError("Переменная DATABASE_URL не установлена")

_pool = None


async def init_db():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=10, statement_cache_size=0
        )
    async with _pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                elo_rating INTEGER DEFAULT 1000,
                games_played INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                is_banned BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')
        # Миграция: добавляем колонку is_banned, если её нет
        await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE;')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id SERIAL PRIMARY KEY,
                winner_id BIGINT NOT NULL,
                loser_id BIGINT NOT NULL,
                winner_elo_change INTEGER DEFAULT 0,
                loser_elo_change INTEGER DEFAULT 0,
                played_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS challenges (
                id SERIAL PRIMARY KEY,
                challenger_id BIGINT NOT NULL,
                opponent_id BIGINT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS pending_results (
                id SERIAL PRIMARY KEY,
                winner_id BIGINT NOT NULL,
                loser_id BIGINT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        ''')


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# === USERS ===

async def get_or_create_user(telegram_id: int, username: str, full_name: str):
    async with _pool.acquire() as conn:
        user = await conn.fetchrow('SELECT * FROM users WHERE telegram_id = $1', telegram_id)
        if not user:
            await conn.execute(
                'INSERT INTO users (telegram_id, username, full_name) VALUES ($1, $2, $3)',
                telegram_id, username, full_name
            )
            user = await conn.fetchrow('SELECT * FROM users WHERE telegram_id = $1', telegram_id)
        else:
            if user['username'] != username or user['full_name'] != full_name:
                await conn.execute(
                    'UPDATE users SET username = $1, full_name = $2 WHERE telegram_id = $3',
                    username, full_name, telegram_id
                )
                user = await conn.fetchrow('SELECT * FROM users WHERE telegram_id = $1', telegram_id)
        return user


async def get_user_profile(telegram_id: int):
    async with _pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM users WHERE telegram_id = $1', telegram_id)


async def get_top_players(limit: int = 10):
    async with _pool.acquire() as conn:
        # Исключаем забаненных
        return await conn.fetch(
            'SELECT * FROM users WHERE is_banned = FALSE ORDER BY elo_rating DESC, telegram_id ASC LIMIT $1',
            limit
        )


async def get_all_users(limit: int = 30):
    async with _pool.acquire() as conn:
        return await conn.fetch(
            'SELECT telegram_id, username, full_name, elo_rating FROM users '
            'WHERE is_banned = FALSE '
            'ORDER BY elo_rating DESC, telegram_id ASC LIMIT $1',
            limit
        )


# === ELO ===

def calculate_elo_change(winner_elo: int, loser_elo: int, k_factor: int = K_FACTOR) -> tuple:
    expected_winner = 1 / (1 + math.pow(10, (loser_elo - winner_elo) / 400))
    expected_loser = 1 / (1 + math.pow(10, (winner_elo - loser_elo) / 400))
    winner_change = round(k_factor * (1 - expected_winner))
    loser_change = round(k_factor * (0 - expected_loser))
    return winner_change, loser_change


# === MATCHES ===

async def record_match(winner_id: int, loser_id: int):
    if winner_id == loser_id:
        return False, "Нельзя записать матч с самим собой"

    async with _pool.acquire() as conn:
        # Проверяем, не забанены ли игроки
        w_user = await conn.fetchrow('SELECT is_banned FROM users WHERE telegram_id = $1', winner_id)
        l_user = await conn.fetchrow('SELECT is_banned FROM users WHERE telegram_id = $1', loser_id)
        if not w_user or not l_user:
            return False, "Один из игроков не найден в базе"
        if w_user['is_banned'] or l_user['is_banned']:
            return False, "Один из игроков заблокирован"

        existing = await conn.fetchrow(
            f'''SELECT id FROM matches 
                WHERE ((winner_id = $1 AND loser_id = $2) OR (winner_id = $3 AND loser_id = $4))
                AND played_at > NOW() - INTERVAL '{MATCH_COOLDOWN_MINUTES} minutes' ''',
            winner_id, loser_id, loser_id, winner_id
        )
        if existing:
            return False, f"Матч между вами уже записан менее {MATCH_COOLDOWN_MINUTES} минут назад"

        winner_data = await conn.fetchrow('SELECT elo_rating FROM users WHERE telegram_id = $1', winner_id)
        loser_data = await conn.fetchrow('SELECT elo_rating FROM users WHERE telegram_id = $1', loser_id)

        w_change, l_change = calculate_elo_change(winner_data['elo_rating'], loser_data['elo_rating'])
        new_winner_elo = winner_data['elo_rating'] + w_change
        new_loser_elo = loser_data['elo_rating'] + l_change

        async with conn.transaction():
            await conn.execute(
                'UPDATE users SET elo_rating = $1, games_played = games_played + 1, wins = wins + 1 WHERE telegram_id = $2',
                new_winner_elo, winner_id
            )
            await conn.execute(
                'UPDATE users SET elo_rating = $1, games_played = games_played + 1 WHERE telegram_id = $2',
                new_loser_elo, loser_id
            )
            await conn.execute(
                'INSERT INTO matches (winner_id, loser_id, winner_elo_change, loser_elo_change) VALUES ($1, $2, $3, $4)',
                winner_id, loser_id, w_change, l_change
            )

        return True, (new_winner_elo, new_loser_elo, w_change, l_change)


async def get_match_history(telegram_id: int, limit: int = 10):
    async with _pool.acquire() as conn:
        # Используем LEFT JOIN, чтобы история работала, даже если игрок был удален
        return await conn.fetch('''
            SELECT m.id, m.winner_id, m.loser_id, m.winner_elo_change, m.loser_elo_change, m.played_at,
                   COALESCE(u1.full_name, 'Удаленный игрок') as winner_name, u1.username as winner_username,
                   COALESCE(u2.full_name, 'Удаленный игрок') as loser_name, u2.username as loser_username
            FROM matches m
            LEFT JOIN users u1 ON m.winner_id = u1.telegram_id
            LEFT JOIN users u2 ON m.loser_id = u2.telegram_id
            WHERE m.winner_id = $1 OR m.loser_id = $1
            ORDER BY m.played_at DESC LIMIT $2
        ''', telegram_id, limit)


async def get_h2h_stats(user_id1: int, user_id2: int):
    async with _pool.acquire() as conn:
        w1 = await conn.fetchval('SELECT COUNT(*) FROM matches WHERE winner_id = $1 AND loser_id = $2', user_id1, user_id2)
        w2 = await conn.fetchval('SELECT COUNT(*) FROM matches WHERE winner_id = $1 AND loser_id = $2', user_id2, user_id1)
        return w1, w2


# === RANK / TOP ===

async def get_total_players() -> int:
    async with _pool.acquire() as conn:
        return await conn.fetchval('SELECT COUNT(*) FROM users WHERE is_banned = FALSE')


async def get_user_rank(telegram_id: int):
    async with _pool.acquire() as conn:
        row = await conn.fetchrow('SELECT elo_rating FROM users WHERE telegram_id = $1', telegram_id)
        if not row:
            return None
        count = await conn.fetchval(
            'SELECT COUNT(*) FROM users WHERE is_banned = FALSE AND (elo_rating > $1 OR (elo_rating = $1 AND telegram_id < $2))',
            row['elo_rating'], telegram_id
        )
        return count + 1


async def get_players_upto(max_rank: int):
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT telegram_id, username, full_name, elo_rating FROM users '
            'WHERE is_banned = FALSE '
            'ORDER BY elo_rating DESC, telegram_id ASC LIMIT $1',
            max_rank
        )
        return [(i + 1, r['telegram_id'], r['username'], r['full_name'], r['elo_rating']) for i, r in enumerate(rows)]


async def get_players_above(telegram_id: int, max_above: int = CHALLENGE_RANGE):
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT telegram_id, username, full_name, elo_rating FROM users '
            'WHERE is_banned = FALSE '
            'ORDER BY elo_rating DESC, telegram_id ASC'
        )
        user_index = None
        for i, row in enumerate(rows):
            if row['telegram_id'] == telegram_id:
                user_index = i
                break
        if user_index is None or user_index == 0:
            return []
        start = max(0, user_index - max_above)
        result = []
        for i in range(user_index - 1, start - 1, -1):
            r = rows[i]
            result.append((i + 1, r['telegram_id'], r['username'], r['full_name'], r['elo_rating']))
        return result


# === CHALLENGES ===

async def create_challenge(challenger_id: int, opponent_id: int):
    if challenger_id == opponent_id:
        return False, "Нельзя вызвать самого себя"
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM challenges WHERE status = 'pending' AND created_at < NOW() - INTERVAL '24 hours'")
        existing = await conn.fetchrow(
            "SELECT id FROM challenges WHERE challenger_id = $1 AND opponent_id = $2 AND status = 'pending'",
            challenger_id, opponent_id
        )
        if existing:
            return False, "Ты уже отправил вызов этому игроку, жди ответа"
        challenge_id = await conn.fetchval(
            'INSERT INTO challenges (challenger_id, opponent_id) VALUES ($1, $2) RETURNING id',
            challenger_id, opponent_id
        )
        return True, challenge_id


async def get_challenge(challenge_id: int):
    async with _pool.acquire() as conn:
        return await conn.fetchrow('SELECT id, challenger_id, opponent_id, status FROM challenges WHERE id = $1', challenge_id)


async def update_challenge_status(challenge_id: int, status: str):
    async with _pool.acquire() as conn:
        await conn.execute('UPDATE challenges SET status = $1 WHERE id = $2', status, challenge_id)


# === PENDING RESULTS ===

async def create_pending_result(winner_id: int, loser_id: int):
    if winner_id == loser_id:
        return False, "Нельзя выбрать самого себя"
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM pending_results WHERE created_at < NOW() - INTERVAL '24 hours'")
        existing = await conn.fetchrow('SELECT id FROM pending_results WHERE winner_id = $1 AND loser_id = $2', winner_id, loser_id)
        if existing:
            return False, "Результат уже ожидает подтверждения от этого игрока"
        pending_id = await conn.fetchval(
            'INSERT INTO pending_results (winner_id, loser_id) VALUES ($1, $2) RETURNING id',
            winner_id, loser_id
        )
        return True, pending_id


async def get_pending_result(pending_id: int):
    async with _pool.acquire() as conn:
        return await conn.fetchrow('SELECT id, winner_id, loser_id FROM pending_results WHERE id = $1', pending_id)


async def delete_pending_result(pending_id: int):
    async with _pool.acquire() as conn:
        await conn.execute('DELETE FROM pending_results WHERE id = $1', pending_id)


# === ADMIN FUNCTIONS ===

async def admin_ban_user(telegram_id: int, ban: bool = True):
    async with _pool.acquire() as conn:
        status = await conn.execute('UPDATE users SET is_banned = $1 WHERE telegram_id = $2', ban, telegram_id)
        return status != "UPDATE 0"

async def admin_delete_user(telegram_id: int):
    async with _pool.acquire() as conn:
        # Удаляем пользователя из таблицы. Матчи остаются (имена будут "Удаленный игрок").
        status = await conn.execute('DELETE FROM users WHERE telegram_id = $1', telegram_id)
        # Чистим его зависшие вызовы и запросы
        await conn.execute('DELETE FROM challenges WHERE challenger_id = $1 OR opponent_id = $1', telegram_id)
        await conn.execute('DELETE FROM pending_results WHERE winner_id = $1 OR loser_id = $1', telegram_id)
        return status != "DELETE 0"
