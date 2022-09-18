import functools
import time
import telebot
import telebot.types as types
from collections import defaultdict
from typing import Callable, Optional
from dataclasses import dataclass

from .conversation import Conversation, ConversationQuestion, ClientError, FormatError
from .models import DatabaseConnector, AdminModel

@dataclass
class ConversationSelector:
    conversation: Conversation
    callback: Callable[[int, dict], None]
    conversation_condition: Callable[[types.Message], bool]


class ConversationHandler:
    __slots__ = [
        "_bot",
        "_admins",
        "_psychologists",
        "_answers",
        "_last_q_wo_callback_in_conv",
        "_conversation_pool",
    ]

    def __init__(self, bot: telebot.TeleBot, admins: list[str], psychologists: list[str]):
        self._bot: telebot.TeleBot = bot
        self._answers: dict[int, dict] = defaultdict(dict)  # chat_id -> client description
        self._conversation_pool: list[ConversationSelector] = []
        self._admins: set[str] = admins
        self._psychologists: set[str] = psychologists

        self._last_q_wo_callback_in_conv: dict[int, int] = defaultdict(lambda: 0)

        self._bot.register_message_handler(self._start_conversation, commands=["start"])

    def add_admin_handle(self, command: str, callback: Callable[[types.Message], None]):
        def admin_filter(message: types.Message) -> bool:
            return message.from_user.username in self._admins and message.text.startswith(command)
        self._bot.register_message_handler(callback, func=admin_filter)

    def add_conversation(self, conversation: Conversation, callback: Callable[[int, dict], None], path_filter: Callable[[types.Message], bool]):
        self._conversation_pool.append(ConversationSelector(conversation, callback, path_filter))

    def _start_conversation(self, message: types.Message):
        assert len(self._conversation_pool) == 1
        if message.from_user.username in self._admins:
            self._bot.send_message(message.chat.id, "Вы администратор. Вы можете вводить две команды:\n/dump - скачать базу в Excel\n/add {имя пользователя}")
            return

        maybe_conv_idx: Optional[int] = self._select_conversation_idx(message)
        if maybe_conv_idx is None:
            return

        conv_idx: int = maybe_conv_idx

        if self._conversation_pool[conv_idx].conversation.initial_message is not None:
            self._bot.send_message(message.chat.id, self._conversation_pool[conv_idx].conversation.initial_message)
            time.sleep(0.5)
        self._ask_client_question(conv_idx, 0, message.chat.id)

    def _select_conversation_idx(self, message: types.Message) -> Optional[int]:
        for idx, selector in enumerate(self._conversation_pool):
            if selector.conversation_condition(message):
                return idx

    def _get_conversation_question(self, conversation_idx: int, question_idx: int) -> ConversationQuestion:
        return self._conversation_pool[conversation_idx].conversation.conversation[question_idx]

    def _ask_client_question(self, conv_idx: int, question_idx: int, chat_id: int):
        question = self._get_conversation_question(conv_idx, question_idx)
        if question.answer_options is not None:
            keyboard = types.InlineKeyboardMarkup()
            callbacks: set[str] = set()
            for option_text, option_callback in question.answer_options:
                keyboard.add(types.InlineKeyboardButton(text=option_text, callback_data=option_callback))
                if self._last_q_wo_callback_in_conv[conv_idx] <= question_idx:
                    callbacks.add(option_callback)

            if self._last_q_wo_callback_in_conv[conv_idx] <= question_idx:
                self._last_q_wo_callback_in_conv[conv_idx] += 1
                self._bot.register_callback_query_handler(functools.partial(self._save_callback_as_text, conv_idx, question_idx),
                                                          lambda callback: callback.data in callbacks)

            self._bot.send_message(chat_id, question.question_text, reply_markup=keyboard)
        else:
            self._bot.send_message(chat_id, question.question_text)
            self._bot.register_next_step_handler_by_chat_id(chat_id, functools.partial(self._receive_client_answer, conv_idx, question_idx))

    def _receive_client_answer(self, conv_idx: int, question_idx: int, message: types.Message):
        question = self._get_conversation_question(conv_idx, question_idx)
        received_answer: str = message.text
        if question.answer_callback is not None:
            try:
                received_answer = question.answer_callback(received_answer)
            except FormatError as e:
                self._bot.send_message(message.chat.id, str(e))
                time.sleep(0.5)
                self._ask_client_question(conv_idx, question_idx, message.chat.id)
                return
            except ClientError as e:
                self._bot.send_message(message.chat.id, str(e))
                del self._answers[message.chat.id]
                return

        self._answers[message.chat.id][question.question_key] = received_answer
        if question_idx + 1 == len(self._conversation_pool[conv_idx].conversation.conversation):
            if self._conversation_pool[conv_idx].conversation.ending_message is not None:
                self._bot.send_message(message.chat.id, self._conversation_pool[conv_idx].conversation.ending_message)

            self._conversation_pool[conv_idx].callback(message.chat, self._answers[message.chat.id])
            del self._answers[message.chat.id]
        else:
            self._ask_client_question(conv_idx, question_idx + 1, message.chat.id)

    def _save_callback_as_text(self, conv_idx: int, question_idx: int, callback: types.CallbackQuery):
        self._bot.edit_message_reply_markup(callback.message.chat.id, callback.message.id)
        question = self._get_conversation_question(conv_idx, question_idx)
        self._answers[callback.message.chat.id][question.question_key] = callback.data

        if question_idx + 1 == len(self._conversation_pool[conv_idx].conversation.conversation):
            if self._conversation_pool[conv_idx].conversation.ending_message is not None:
                self._bot.send_message(callback.message.chat.id, self._conversation_pool[conv_idx].conversation.ending_message)

            self._conversation_pool[conv_idx].callback(callback.message.chat, self._answers[callback.message.chat.id])
            del self._answers[callback.message.chat.id]
        else:
            self._ask_client_question(conv_idx, question_idx + 1, callback.message.chat.id)

