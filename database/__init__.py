# database/__init__.py
from database.pool import init_pool, close_pool, get_pool

from database.users import (
    get_or_create_user,
    get_user_profile,
    get_all_users,
    admin_ban_user,
    admin_delete_user,
)

from database.matches import (
    record_match,
    get_match_history,
    get_h2h_stats,
    get_top_players,
    get_user_rank,
    get_total_players,
    get_players_upto,
    get_players_above,
    calculate_elo_change,
)

from database.challenges import (
    create_challenge,
    get_challenge,
    update_challenge_status,
    create_pending_result,
    get_pending_result,
    delete_pending_result,
)


async def init_db():
    await init_pool()
    pool = get_pool()
    async with pool.acquire() as conn:
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
