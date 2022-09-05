import os
import sys
import telebot
from telebot import types

from src.models import ClientModel, PsychologistModel, AdminModel, DatabaseConnector
from src.conversation_handler import ConversationHandler
from src.psychologist_matcher import PsychologistMatcher
from src.dump_clients import dump_db


def main():
    print("Bot started", file=sys.stderr)
    db_connector = DatabaseConnector(os.getenv("DB_RECIPE"))
    bot = telebot.TeleBot(os.getenv("BOT_TOKEN"), threaded=False)

    psychologists_map = db_connector.list_psychologists()
    ps_matcher = PsychologistMatcher(bot, db_connector, psychologists_map)

    admins = ["zhantaram", "Assem_Kamitova", "uramaz"]
    conversation_handler = ConversationHandler(bot, admins)

    def add_psychologist_handle(message: types.Message):
        # /add zhalgas
        db_connector.merge_row(AdminModel(admin_chat_id=message.chat.id))
        psychologist_username: str = message.text.split()[-1]
        if psychologist_username.startswith('@'):
            psychologist_username = psychologist_username[1:]
        db_connector.merge_row(PsychologistModel(username=psychologist_username))
        bot.send_message(message.chat.id, "Психолог добавлен. Теперь ему надо пройти анкету")

    conversation_handler.add_admin_handle("/add", add_psychologist_handle)

    def dump_data_handle(message: types.Message):
        # /dump
        db_connector.merge_row(AdminModel(admin_chat_id=message.chat.id))
        path_to_file: str = dump_db(db_connector)
        with open(path_to_file, 'rb') as inp:
            bot.send_document(message.chat.id, inp)

    conversation_handler.add_admin_handle("/dump", dump_data_handle)

    def psychologist_conversation_callback(chat: types.Chat, ps_answers: dict):
        psychologist = PsychologistModel.create_pyschologist_from_answers(chat.id, chat.username, ps_answers)
        db_connector.merge_row(psychologist)
        psychologists_map.append(psychologist)

    conversation_handler.add_conversation(
        PsychologistModel.create_psychologist_conversation(),
        psychologist_conversation_callback,
        lambda message: message.from_user.username in db_connector.get_ps_usernames(),
    )

    def client_conversation_callback(chat: types.Chat, client_answers: dict):
        client = ClientModel.create_client_from_answers(chat.id, client_answers)
        db_connector.merge_row(client)
        ps_matcher.match_client(client)

    conversation_handler.add_conversation(
        ClientModel.create_client_conversation(),
        client_conversation_callback,
        lambda message: message.from_user.username not in db_connector.get_ps_usernames() and db_connector.lookup_client(message.chat.id) is None,
    )

    bot.infinity_polling()


if __name__ == "__main__":
    main()
