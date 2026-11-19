# database/challenges.py
from database.pool import get_pool


async def create_challenge(challenger_id: int, opponent_id: int):
    if challenger_id == opponent_id:
        return False, "Нельзя вызвать самого себя"
    pool = get_pool()
    async with pool.acquire() as conn:
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
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT id, challenger_id, opponent_id, status FROM challenges WHERE id = $1', challenge_id)


async def update_challenge_status(challenge_id: int, status: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute('UPDATE challenges SET status = $1 WHERE id = $2', status, challenge_id)


async def create_pending_result(winner_id: int, loser_id: int):
    if winner_id == loser_id:
        return False, "Нельзя выбрать самого себя"
    pool = get_pool()
    async with pool.acquire() as conn:
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
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT id, winner_id, loser_id FROM pending_results WHERE id = $1', pending_id)


async def delete_pending_result(pending_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM pending_results WHERE id = $1', pending_id)
