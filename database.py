import aiosqlite
import os
from datetime import datetime

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
