   import os
   import logging
   import asyncio
   from aiogram import Bot, Dispatcher, types
   from aiogram.filters import CommandStart

   # Включаем простые логи, чтобы видеть, что бот работает
   logging.basicConfig(level=logging.INFO)

   # Берем токен из настроек сервера (мы добавим его на следующем шаге)
   BOT_TOKEN = os.getenv("BOT_TOKEN")

   # Создаем объекты бота и диспетчера
   bot = Bot(token=BOT_TOKEN)
   dp = Dispatcher()

   # Команда /start
   @dp.message(CommandStart())
   async def cmd_start(message: types.Message):
       user_name = message.from_user.full_name
       await message.answer(
           f"Привет, {user_name}! 🎱\n\n"
           f"Я твой бильярдный помощник.\n"
           f"Сейчас я на стадии разработки, но скоро здесь появится:\n"
           f"🏆 Лестница вызовов\n"
           f"📊 Турнирные сетки\n"
           f"📍 Поиск соперников в Могилёве"
       )

   # Главная функция запуска
   async def main():
       print("Бот запущен и ожидает сообщения...")
       await dp.start_polling(bot)

   if __name__ == "__main__":
       asyncio.run(main())
