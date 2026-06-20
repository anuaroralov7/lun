import telebot
import time
import threading
import requests
import datetime
from telebot import types

# --- НАСТРОЙКИ ---
BOT_TOKEN = '8862990122:AAFzkr4Vu8GD6NOhPgwfm0L7YrOD_hZGp2k'
USER_A_ID = 5275807318  # ID Первого пользователя (Отправитель: seleminya / lunyaa)
USER_B_ID = 927472658   # ID Второго пользователя (Получатель: anuaroralov)
# -----------------

bot = telebot.TeleBot(BOT_TOKEN)

import os
from telebot import apihelper
if os.environ.get('PYTHONANYWHERE_SITE') or os.path.exists('/home/anuar'):
    apihelper.proxy = {'https': 'http://proxy.server:3128'}

# Флаг состояния сирены
is_alarm_active = False

# Функция для циклической отправки сообщений (запускается в отдельном потоке)
def alarm_loop():
    global is_alarm_active
    count = 0
    max_alerts = 60  # Ограничение: 5 минут (60 раз по 5 секунд), чтобы не спамить вечно

    # Создаем кнопку "Выключить" под каждым сообщением для получателя
    markup = types.InlineKeyboardMarkup()
    btn_stop = types.InlineKeyboardButton("🔕 ВЫКЛЮЧИТЬ СИРЕНУ", callback_data="stop_alarm")
    markup.add(btn_stop)

    while is_alarm_active and count < max_alerts:
        try:
            bot.send_message(
                USER_B_ID, 
                f"🚨 ВНИМАНИЕ! СИГНАЛ ТРЕВОГИ! #{count + 1}", 
                reply_markup=markup
            )
        except Exception as e:
            print(f"Ошибка отправки сообщения: {e}")
        
        count += 1
        time.sleep(5)  # Интервал спама в секундах

    if is_alarm_active:  # Если цикл завершился по лимиту времени
        is_alarm_active = False
        bot.send_message(USER_A_ID, "⚠️ Сирена автоматически отключена по тайм-ауту (прошло 5 минут).")
        bot.send_message(USER_B_ID, "🔕 Сирена автоматически отключена.")

# Функция фоновых напоминаний (ежедневные игры)
def reminder_loop():
    print("Поток напоминаний успешно запущен...")
    while True:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            today_str = now_utc.strftime('%Y-%m-%d')
            
            # Получаем список пользователей из Firestore REST API
            users_res = requests.get('https://firestore.googleapis.com/v1/projects/lunaya-app/databases/(default)/documents/users')
            users = []
            if users_res.status_code == 200:
                users_data = users_res.json()
                for d in users_data.get('documents', []):
                    fields = d.get('fields', {})
                    username = d.get('name', '').split('/')[-1].lower()
                    users.append({
                        'username': username,
                        'telegramChatId': fields.get('telegramChatId', {}).get('stringValue'),
                        'lastPlayedDate': fields.get('lastPlayedDate', {}).get('stringValue'),
                        'dailyReminderDate': fields.get('dailyReminderDate', {}).get('stringValue'),
                    })
            
            # 1. Ежедневное напоминание о игре
            # Срабатывает в промежутке 18:30 - 18:38 UTC (23:30 - 23:38 по времени UTC+5)
            if now_utc.hour == 18 and 30 <= now_utc.minute <= 38:
                for user in users:
                    if not user['telegramChatId']:
                        continue
                    has_played_today = user['lastPlayedDate'] == today_str
                    already_reminded = user['dailyReminderDate'] == today_str
                    
                    if not has_played_today and not already_reminded:
                        try:
                            bot.send_message(
                                user['telegramChatId'], 
                                '🎮 <b>Не забудь сыграть!</b>\nЕжедневная игра уже ждет тебя, заходи за монетами! 🌕', 
                                parse_mode='HTML'
                            )
                            # Обновляем dailyReminderDate в БД
                            url = f"https://firestore.googleapis.com/v1/projects/lunaya-app/databases/(default)/documents/users/{user['username']}?updateMask.fieldPaths=dailyReminderDate"
                            data = { "fields": { "dailyReminderDate": { "stringValue": today_str } } }
                            requests.patch(url, json=data)
                        except Exception as e:
                            print(f"Ошибка отправки игрового напоминания для {user['username']}: {e}")
                            
        except Exception as e:
            print(f"Ошибка в цикле напоминаний: {e}")
        
        # Спим 5 минут перед следующей проверкой
        time.sleep(300)

# Обработка команды /start и привязки к БД
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = str(message.chat.id)
    tg_username = message.from_user.username or ''
    
    parts = message.text.split()
    if len(parts) > 1:
        username = parts[1].lower()
        try:
            if username == 'admin':
                url = 'https://firestore.googleapis.com/v1/projects/lunaya-app/databases/(default)/documents/settings/telegram?updateMask.fieldPaths=adminChatId'
                data = { "fields": { "adminChatId": { "stringValue": chat_id } } }
                res = requests.patch(url, json=data)
                if res.status_code == 200:
                    bot.send_message(chat_id, "✅ Успешно! Этот чат теперь привязан как Админ.")
                else:
                    bot.send_message(chat_id, f"❌ Ошибка Firestore (код {res.status_code}) при привязке админа.")
            else:
                update_paths = 'updateMask.fieldPaths=telegramChatId'
                fields = { "telegramChatId": { "stringValue": chat_id } }
                if tg_username:
                    update_paths += '&updateMask.fieldPaths=telegramUsername'
                    fields["telegramUsername"] = { "stringValue": tg_username }
                
                url = f"https://firestore.googleapis.com/v1/projects/lunaya-app/databases/(default)/documents/users/{username}?{update_paths}"
                data = { "fields": fields }
                res = requests.patch(url, json=data)
                if res.status_code == 200:
                    bot.send_message(chat_id, f"✅ Аккаунт {parts[1]} успешно привязан к боту! Теперь вы будете получать уведомления.")
                else:
                    bot.send_message(chat_id, f"❌ Ошибка Firestore (код {res.status_code}) при привязке {parts[1]}.")
        except Exception as e:
            print(f"Ошибка привязки: {e}")
            bot.send_message(chat_id, "❌ Произошла ошибка при связывании с базой данных.")
        return

    int_chat_id = int(chat_id)
    if int_chat_id == USER_A_ID:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn_alert = types.KeyboardButton("🚨 ЗАПУСТИТЬ СИРЕНУ")
        markup.add(btn_alert)
        bot.send_message(chat_id, "Привет! Используйте кнопку ниже для отправки сигнала.", reply_markup=markup)
    elif int_chat_id == USER_B_ID:
        bot.send_message(chat_id, "Привет! Вы настроены как получатель сирены. Ожидайте сигналов.")
    else:
        bot.send_message(chat_id, "Доступ ограничен. Этот бот настроен только для двух конкретных пользователей.")

# Обработка кнопки "Запустить сирену"
@bot.message_handler(func=lambda message: message.chat.id == USER_A_ID and message.text == "🚨 ЗАПУСТИТЬ СИРЕНУ")
def trigger_alarm(message):
    global is_alarm_active
    
    if is_alarm_active:
        bot.send_message(USER_A_ID, "Сирена уже работает!")
        return

    is_alarm_active = True
    bot.send_message(USER_A_ID, "🔴 Сирена запущена. Отправляем сигналы...")
    
    alarm_thread = threading.Thread(target=alarm_loop)
    alarm_thread.start()

# Обработка кнопки "Выключить сирену"
@bot.callback_query_handler(func=lambda call: call.data == "stop_alarm")
def stop_alarm_callback(call):
    global is_alarm_active
    
    if call.message.chat.id == USER_B_ID:
        if is_alarm_active:
            is_alarm_active = False
            bot.edit_message_reply_markup(chat_id=USER_B_ID, message_id=call.message.message_id, reply_markup=None)
            bot.send_message(USER_B_ID, "✅ Вы выключили сирену.")
            bot.send_message(USER_A_ID, "🟢 Второй пользователь отключил сирену.")
        else:
            bot.answer_callback_query(call.id, "Сирена уже выключена.")

# Запуск бота
if __name__ == '__main__':
    # Запуск фонового потока для ежедневных напоминаний и дедлайнов
    reminders_thread = threading.Thread(target=reminder_loop, daemon=True)
    reminders_thread.start()

    print("Бот успешно запущен...")
    bot.infinity_polling()
