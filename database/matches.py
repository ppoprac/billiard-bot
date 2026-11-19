# database/matches.py
import math

from config import K_FACTOR, MATCH_COOLDOWN_MINUTES, CHALLENGE_RANGE
from database.pool import get_pool


def calculate_elo_change(winner_elo: int, loser_elo: int, k_factor: int = K_FACTOR) -> tuple:
    expected_winner = 1 / (1 + math.pow(10, (loser_elo - winner_elo) / 400))
    expected_loser = 1 / (1 + math.pow(10, (winner_elo - loser_elo) / 400))
    winner_change = round(k_factor * (1 - expected_winner))
    loser_change = round(k_factor * (0 - expected_loser))
    return winner_change, loser_change


async def record_match(winner_id: int, loser_id: int):
    if winner_id == loser_id:
        return False, "Нельзя записать матч с самим собой"

    pool = get_pool()
    async with pool.acquire() as conn:
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
    pool = get_pool()
    async with pool.acquire() as conn:
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
    pool = get_pool()
    async with pool.acquire() as conn:
        w1 = await conn.fetchval('SELECT COUNT(*) FROM matches WHERE winner_id = $1 AND loser_id = $2', user_id1, user_id2)
        w2 = await conn.fetchval('SELECT COUNT(*) FROM matches WHERE winner_id = $1 AND loser_id = $2', user_id2, user_id1)
        return w1, w2


async def get_top_players(limit: int = 10):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            'SELECT * FROM users WHERE is_banned = FALSE ORDER BY elo_rating DESC, telegram_id ASC LIMIT $1',
            limit
        )


async def get_user_rank(telegram_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT elo_rating FROM users WHERE telegram_id = $1', telegram_id)
        if not row:
            return None
        count = await conn.fetchval(
            'SELECT COUNT(*) FROM users WHERE is_banned = FALSE AND (elo_rating > $1 OR (elo_rating = $1 AND telegram_id < $2))',
            row['elo_rating'], telegram_id
        )
        return count + 1


async def get_total_players() -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval('SELECT COUNT(*) FROM users WHERE is_banned = FALSE')


async def get_players_upto(max_rank: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT telegram_id, username, full_name, elo_rating FROM users '
            'WHERE is_banned = FALSE '
            'ORDER BY elo_rating DESC, telegram_id ASC LIMIT $1',
            max_rank
        )
        return [(i + 1, r['telegram_id'], r['username'], r['full_name'], r['elo_rating']) for i, r in enumerate(rows)]


async def get_players_above(telegram_id: int, max_above: int = CHALLENGE_RANGE):
    pool = get_pool()
    async with pool.acquire() as conn:
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
