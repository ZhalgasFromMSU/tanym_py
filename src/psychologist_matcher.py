import time
import functools
import telebot
from telebot import types
from typing import Optional

from . import models
from . import dialogue_texts as texts


class CallbackKeyboard:
    __slots__ = [
        "_keyboard",
    ]

    CALLBACK_DATA = list()
    CALLBACK_OPTIONS = list()

    def __init__(self):
        self._keyboard = types.InlineKeyboardMarkup()
        for button_text, callback_data in zip(self.CALLBACK_OPTIONS, self.CALLBACK_DATA):
            self._keyboard.add(types.InlineKeyboardButton(text=button_text, callback_data=callback_data))

    @classmethod
    def callback_filter(cls, callback: types.CallbackQuery) -> bool:
        return callback.data in cls.CALLBACK_DATA

    @classmethod
    def keyboard(cls) -> types.InlineKeyboardMarkup:
        keyboard = types.InlineKeyboardMarkup()
        for button_text, callback_data in zip(cls.CALLBACK_OPTIONS, cls.CALLBACK_DATA):
            keyboard.add(types.InlineKeyboardButton(text=button_text, callback_data=callback_data))
        return keyboard


class MatchPsychologistCallback(CallbackKeyboard):
    CALLBACK_DATA = [f"MatchPsychologistCallback_{data}" for data in ("take", "dont_take", "status")]
    CALLBACK_OPTIONS = ["Беру", "Не беру", "Статус"]


class ClientAssignedPsCallback(CallbackKeyboard):
    CALLBACK_DATA = [f"ClientAssignedPsCallback_{data}" for data in ("didnt_write", "finished")]
    CALLBACK_OPTIONS = ["Клиент не написал", "Консультация прошла"]


class ClientReviewScoresCallback(CallbackKeyboard):
    CALLBACK_DATA = [f"ClientReviewScoresCallback_{data}" for data in ("1", "2", "3", "4", "5")]
    CALLBACK_OPTIONS = ["1", "2", "3", "4", "5"]


class PsychologistMatcher:
    def __init__(self, bot: telebot.TeleBot, db_connector: models.DatabaseConnector, psychologists_map: list[models.PsychologistModel]):
        self._bot: telebot.TeleBot = bot
        self._db_connector: models.DatabaseConnector = db_connector
        self._ps_map: list[models.PsychologistModel] = psychologists_map

        self._bot.register_callback_query_handler(self._match_callback, MatchPsychologistCallback.callback_filter)
        self._bot.register_callback_query_handler(self._assigned_ps_callback, ClientAssignedPsCallback.callback_filter)
        self._bot.register_callback_query_handler(self._process_score, ClientReviewScoresCallback.callback_filter)

    def match_client(self, client: models.ClientModel):
        for psychologist in self._ps_map:
            if client.lang in psychologist.client_lang and client.sex in psychologist.client_sex and client.pr_type in psychologist.problem_type.split():
                message = self._bot.send_message(psychologist.chat_id, str(client), reply_markup=MatchPsychologistCallback.keyboard())
                self._db_connector.merge_row(models.AssignmentsModel(client_chat_id=client.chat_id, ps_chat_id=psychologist.chat_id, message_id=message.id))

        for admin in self._db_connector.list_admins():
            self._bot.send_message(admin.admin_chat_id, str(client))

    def _match_callback(self, callback: types.CallbackQuery):
        # Psychologist received a message offering a client
        if not callback.data.endswith("status"):
            self._bot.edit_message_reply_markup(callback.message.chat.id, callback.message.id)

        if callback.data.endswith("dont_take"):
            return

        message_id: int = callback.message.id
        ps_chat_id: int = callback.message.chat.id

        assignment: Optional[models.AssignmentsModel] = self._db_connector.lookup_assignment_info(ps_chat_id, message_id)
        if assignment is None:
            self._bot.answer_callback_query(callback_query_id=callback.id, text="Клиента уже забрали")
            return

        client_chat_id: int = assignment.client_chat_id

        if callback.data.endswith("take"):
            self._db_connector.remove_client_assignment_infos(client_chat_id, ps_chat_id_to_leave=ps_chat_id)
            self._bot.answer_callback_query(callback_query_id=callback.id, text="Клиент теперь ваш. Скоро напишет")
            self._bot.send_message(client_chat_id, texts.CLIENT_RULES)
            time.sleep(0.5)
            self._bot.send_message(client_chat_id, f"Психолог @{callback.from_user.username} согласился вам помочь. Пожалуйста, не забудьте оплатить консультацию психологу.")
            self._bot.edit_message_reply_markup(callback.message.chat.id, callback.message.id, reply_markup=ClientAssignedPsCallback.keyboard())
        else:  # callback.data == MatchStageCallbackHelper.STATUS
            self._bot.answer_callback_query(callback_query_id=callback.id, text="Клиент свободен")

    def _assigned_ps_callback(self, callback: types.CallbackQuery):
        # Psychologist took client. Psychologist side conversation
        assignment = self._db_connector.lookup_assignment_info(callback.message.chat.id, callback.message.id)
        assert assignment is not None
        self._bot.edit_message_reply_markup(callback.message.chat.id, callback.message.id)
        if callback.data.endswith("didnt_write"):
            self._bot.send_message(assignment.client_chat_id, "Вы не написали психологу")
            self._db_connector.remove_client_assignment_infos(assignment.client_chat_id)
        else:  # finished
            self._bot.send_message(assignment.client_chat_id, texts.ASK_REVIEW_SCORE_TEXT, reply_markup=ClientReviewScoresCallback.keyboard())

    def _process_score(self, callback: types.CallbackQuery):
        assignment = self._db_connector.lookup_assignment_info_by_client(callback.message.chat.id)
        if assignment is None:
            return

        msg = self._bot.send_message(assignment.client_chat_id, "Для улучшения процессов нам очень важна ваша обратная связь, поэтому, пожалуйста, оставьте развернутый отзыв")
        self._bot.register_next_step_handler(msg, functools.partial(self._process_review, int(callback.data.split('_')[-1])))

    def _process_review(self, score: int, message: types.Message):
        self._db_connector.merge_row(
            models.ClientModel(
                chat_id=message.chat.id,
                score=score,
                review=message.text,
            )
        )
        assignment = self._db_connector.lookup_assignment_info_by_client(message.chat.id)
        psychologist = self._db_connector.lookup_psychologists_by_chat(assignment.ps_chat_id)
        self._bot.send_message(message.chat.id, "Спасибо! Были рады вам помочь")
        if score < 3:
            for admin in self._db_connector.list_admins():
                self._bot.send_message(admin.admin_chat_id, f"Психолог: {psychologist.name}\nОценка: {score}\nОтзыв: {message.text}")
