# database/pool.py
import asyncpg

from config import BASE_URL  # не используется, но пусть будет чисто; можно убрать

# DATABASE_URL берём из окружения
import os
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("Переменная DATABASE_URL не установлена")

_pool = None


async def init_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=10, statement_cache_size=0
        )
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool():
    if _pool is None:
        raise RuntimeError("Пул соединений не инициализирован. Вызови init_pool()")
    return _pool
