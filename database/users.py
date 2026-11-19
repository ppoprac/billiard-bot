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
