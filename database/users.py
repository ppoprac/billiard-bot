# database/users.py
from database.pool import get_pool


async def get_or_create_user(telegram_id: int, username: str, full_name: str):
    pool = get_pool()
    async with pool.acquire() as conn:
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
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM users WHERE telegram_id = $1', telegram_id)


async def get_all_users(limit: int = 30):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            'SELECT telegram_id, username, full_name, elo_rating FROM users '
            'WHERE is_banned = FALSE '
            'ORDER BY elo_rating DESC, telegram_id ASC LIMIT $1',
            limit
        )


async def get_all_users_paginated(offset: int = 0, limit: int = 10, exclude_id: int | None = None):
    """Список пользователей с пагинацией.

    Возвращает (total, rows), где total — общее число игроков
    (с учётом exclude_id), rows — игроки текущей страницы.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        if exclude_id is not None:
            total = await conn.fetchval(
                'SELECT COUNT(*) FROM users WHERE is_banned = FALSE AND telegram_id != $1',
                exclude_id
            )
            rows = await conn.fetch(
                'SELECT telegram_id, username, full_name, elo_rating FROM users '
                'WHERE is_banned = FALSE AND telegram_id != $1 '
                'ORDER BY elo_rating DESC, telegram_id ASC LIMIT $2 OFFSET $3',
                exclude_id, limit, offset
            )
        else:
            total = await conn.fetchval('SELECT COUNT(*) FROM users WHERE is_banned = FALSE')
            rows = await conn.fetch(
                'SELECT telegram_id, username, full_name, elo_rating FROM users '
                'WHERE is_banned = FALSE '
                'ORDER BY elo_rating DESC, telegram_id ASC LIMIT $2 OFFSET $3',
                limit, offset
            )
        return total, rows


async def admin_ban_user(telegram_id: int, ban: bool = True):
    pool = get_pool()
    async with pool.acquire() as conn:
        status = await conn.execute('UPDATE users SET is_banned = $1 WHERE telegram_id = $2', ban, telegram_id)
        return status != "UPDATE 0"


async def admin_delete_user(telegram_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        status = await conn.execute('DELETE FROM users WHERE telegram_id = $1', telegram_id)
        await conn.execute('DELETE FROM challenges WHERE challenger_id = $1 OR opponent_id = $1', telegram_id)
        await conn.execute('DELETE FROM pending_results WHERE winner_id = $1 OR loser_id = $1', telegram_id)
        return status != "DELETE 0"


# === DISCIPLINES ===

async def get_all_disciplines():
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch('SELECT id, slug, name, sort_order FROM disciplines ORDER BY sort_order, id')


async def get_discipline_by_id(discipline_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT id, slug, name, sort_order FROM disciplines WHERE id = $1', discipline_id)


async def get_user_rating(telegram_id: int, discipline_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            'SELECT user_id, discipline_id, elo, games_played, wins '
            'FROM user_ratings WHERE user_id = $1 AND discipline_id = $2',
            telegram_id, discipline_id
        )


async def create_user_rating(telegram_id: int, discipline_id: int, elo: int = 1000):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'INSERT INTO user_ratings (user_id, discipline_id, elo) VALUES ($1, $2, $3) '
            'ON CONFLICT (user_id, discipline_id) DO NOTHING',
            telegram_id, discipline_id, elo
        )


async def set_user_current_discipline(telegram_id: int, discipline_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'UPDATE users SET current_discipline_id = $1 WHERE telegram_id = $2',
            discipline_id, telegram_id
        )


async def ensure_user_rating(telegram_id: int, discipline_id: int):
    """Возвращает запись рейтинга, создавая её при отсутствии."""
    rating = await get_user_rating(telegram_id, discipline_id)
    if rating is None:
        await create_user_rating(telegram_id, discipline_id)
        rating = await get_user_rating(telegram_id, discipline_id)
    return rating
