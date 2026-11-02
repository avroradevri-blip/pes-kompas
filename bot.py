import os
import sys
from pathlib import Path

import telebot
from dotenv import load_dotenv
from telebot import types

from db import notice_word, save_bot_user, unread_count

load_dotenv(Path(__file__).with_name(".env"))

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
SITE = os.environ.get("SITE_URL", "http://127.0.0.1:8080").rstrip("/")

START = (
    "Пёс-Компас сводит хозяина собаки и человека, который может с ней погулять.\n\n"
    "Если собака ваша — оставляете заявку и платите тому, кто откликнется.\n"
    "Если собаки нет — смотрите заявки и зарабатываете на прогулке.\n\n"
    "Кнопка «Откликнуться» открывает чат заявки. "
    "Когда вам пишут, сюда приходит, сколько уведомлений не прочитано."
)

OWNER = (
    "Оставьте заявку: кличка, район, дата и время. У заявки будет свой номер.\n\n"
    "Кто нажмёт «Откликнуться», попадёт в чат этого номера. "
    "Сообщения видны в «Мои заявки». Когда вам ответят, бот напишет, сколько у вас уведомлений.\n\n"
    "О сумме договариваетесь в чате."
)

WALKER = (
    "Откройте список и нажмите «Откликнуться». Сразу откроется чат заявки: "
    "напишите хозяину, когда можете выйти.\n\n"
    "Когда ответят, бот пришлёт, сколько уведомлений не прочитано. "
    "В том сообщении будет кнопка «Открыть чат»."
)

HELP = (
    "«У меня есть собака» — создать заявку. Номер появится в списке и в чате.\n"
    "«Хочу заработать» — список заявок. «Откликнуться» открывает чат.\n\n"
    "Напоминание приходит в этот бот. Чтобы оно вас находило, "
    "в профиле Telegram должен быть ник, и боту нужно один раз написать /start."
)


def menu_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("У меня есть собака", callback_data="role_owner"))
    markup.row(types.InlineKeyboardButton("Хочу заработать", callback_data="role_walker"))
    return markup


def owner_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("Оставить заявку", url=f"{SITE}/new"))
    markup.row(types.InlineKeyboardButton("Мои заявки", url=f"{SITE}/mine"))
    markup.row(types.InlineKeyboardButton("Назад", callback_data="role_menu"))
    return markup


def walker_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("Смотреть заявки", url=f"{SITE}/list"))
    markup.row(types.InlineKeyboardButton("Назад", callback_data="role_menu"))
    return markup


SCREENS = {
    "role_menu": (START, menu_keyboard),
    "role_owner": (OWNER, owner_keyboard),
    "role_walker": (WALKER, walker_keyboard),
}


def remember(user, chat_id):
    if user and user.username:
        save_bot_user(user.username, chat_id)


def with_unread(text, user):
    if not user or not user.username:
        return text
    n = unread_count("@" + user.username)
    if not n:
        return text
    return f"У вас {n} {notice_word(n)}.\n\n" + text


def show_screen(bot, call, key):
    text, keyboard = SCREENS[key]
    remember(call.from_user, call.message.chat.id)
    bot.answer_callback_query(call.id)
    text = with_unread(text, call.from_user)
    try:
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard(),
        )
    except telebot.apihelper.ApiTelegramException:
        bot.send_message(call.message.chat.id, text, reply_markup=keyboard())


def main():
    if not TOKEN:
        print("В .env нет BOT_TOKEN. Сайт при этом можно открыть отдельно.")
        sys.exit(1)

    bot = telebot.TeleBot(TOKEN)
    try:
        bot.set_my_commands(
            [
                types.BotCommand("start", "Собака есть или хочу заработать"),
                types.BotCommand("help", "Чаты и уведомления"),
            ]
        )
        bot.set_my_short_description("Прогулка: заявка, чат, уведомления")
    except telebot.apihelper.ApiTelegramException:
        pass

    @bot.message_handler(commands=["start"])
    def start(message):
        remember(message.from_user, message.chat.id)
        bot.send_message(
            message.chat.id,
            with_unread(START, message.from_user),
            reply_markup=menu_keyboard(),
        )

    @bot.message_handler(commands=["help"])
    def help_cmd(message):
        remember(message.from_user, message.chat.id)
        bot.send_message(
            message.chat.id,
            with_unread(HELP, message.from_user),
            reply_markup=menu_keyboard(),
        )

    @bot.callback_query_handler(func=lambda call: call.data in SCREENS)
    def on_role(call):
        show_screen(bot, call, call.data)

    print(f"Бот запущен. Кнопки открывают {SITE}", flush=True)
    bot.infinity_polling(skip_pending=True, timeout=30)


if __name__ == "__main__":
    main()
