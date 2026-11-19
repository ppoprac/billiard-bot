# database/__init__.py
from database.pool import init_pool, close_pool, get_pool

from database.users import (
    get_or_create_user,
    get_user_profile,
    get_all_users,
    admin_ban_user,
    admin_delete_user,
    get_all_disciplines,
    get_discipline_by_id,
    get_user_rating,
    create_user_rating,
    set_user_current_discipline,
    ensure_user_rating,
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
    get_active_challenges_for_user,
    update_challenge_status,
    create_pending_result,
    get_pending_result,
    delete_pending_result,
)


DISCIPLINES_SEED = [
    ("free_pyramid", "Свободная пирамида"),
    ("combined_pyramid", "Комбинированная пирамида"),
    ("dynamic_pyramid", "Динамичная пирамида"),
    ("classic_pyramid", "Классическая русская пирамида"),
    ("pool_8", "Пул‑8"),
    ("pool_9", "Пул‑9"),
    ("pool_10", "Пул‑10"),
    ("pool_14_1", "Пул‑14+1 (стрейт‑пул)"),
    ("snooker_15", "Снукер (15 красных)"),
    ("snooker_6", "Снукер (6 красных)"),
    ("snooker_1", "Снукер (1 красный)"),
    ("carom", "Карамболь"),
]


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

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS disciplines (
                id SERIAL PRIMARY KEY,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0
            )
        ''')

        for idx, (slug, name) in enumerate(DISCIPLINES_SEED, start=1):
            await conn.execute(
                '''
                INSERT INTO disciplines (slug, name, sort_order)
                VALUES ($1, $2, $3)
                ON CONFLICT (slug) DO UPDATE
                    SET name = EXCLUDED.name,
                        sort_order = EXCLUDED.sort_order
                ''',
                slug, name, idx
            )

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_ratings (
                user_id BIGINT NOT NULL,
                discipline_id INTEGER NOT NULL,
                elo INTEGER DEFAULT 1000,
                games_played INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, discipline_id),
                FOREIGN KEY (discipline_id) REFERENCES disciplines(id)
            )
        ''')

        await conn.execute('''
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS current_discipline_id INTEGER
            REFERENCES disciplines(id) DEFAULT 1
        ''')

        await conn.execute('''
            ALTER TABLE matches
            ADD COLUMN IF NOT EXISTS discipline_id INTEGER
            REFERENCES disciplines(id) DEFAULT 1
        ''')

        # Этап 3.5 — дисциплина у вызовов и pending_results
        await conn.execute('''
            ALTER TABLE challenges
            ADD COLUMN IF NOT EXISTS discipline_id INTEGER
            REFERENCES disciplines(id) DEFAULT 1
        ''')
        await conn.execute('''
            ALTER TABLE pending_results
            ADD COLUMN IF NOT EXISTS discipline_id INTEGER
            REFERENCES disciplines(id) DEFAULT 1
        ''')
