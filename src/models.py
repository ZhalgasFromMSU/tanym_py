from __future__ import annotations

import sys
import sqlalchemy
import sqlalchemy.sql.expression as expression
from sqlalchemy import types
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from typing import Union, Optional

import src.dialogue_texts as texts
from src.conversation import ConversationQuestion, Conversation, FormatError, ClientError

Base = declarative_base()


class ClientModel(Base):
    __tablename__ = "clients"

    chat_id = sqlalchemy.Column(types.BigInteger, primary_key=True)
    date = sqlalchemy.Column(types.DateTime)

    name = sqlalchemy.Column(types.Text)
    lang = sqlalchemy.Column(types.Enum("ru", "kz", name="lang"))
    sex = sqlalchemy.Column(types.Enum("boy", "girl", name="sex"))
    age = sqlalchemy.Column(types.Integer)
    city = sqlalchemy.Column(types.Text)

    pr_type = sqlalchemy.Column(types.Text)
    pr_descr = sqlalchemy.Column(types.Text)

    score = sqlalchemy.Column(types.Integer)
    review = sqlalchemy.Column(types.Text)

    def __repr__(self) -> str:
        return "\n".join([
            f"Имя: {self.name}",
            f"Возраст: {self.age}",
            f"Город: {self.city}",
            f"Тип проблемы: {texts.PROBLEM_TYPES_STR[int(self.pr_type)]}",
            f"Описание: {self.pr_descr}",
        ])

    @staticmethod
    def create_client_conversation() -> Conversation:
        client_conversation = Conversation()
        client_conversation.add_initial_message(texts.GREET_CLIENT)

        # name
        client_conversation.add_question(ConversationQuestion(
            question_key="name",
            question_text="Как вас зовут?",
        ))

        # lang
        client_conversation.add_question(ConversationQuestion(
            question_key="lang",
            question_text="На каком языке хотите получить консультацию?",
            answer_options=[("Русский", "ru"), ("Казахский", "kz")],
        ))

        # sex
        client_conversation.add_question(ConversationQuestion(
            question_key="sex",
            question_text="Ваш пол?",
            answer_options=[("Мужской", "boy"), ("Женский", "girl")],
        ))

        # age
        def age_question_callback(client_answer: str) -> int:
            if not client_answer.isdigit():
                raise FormatError("Введите возраст числом")

            if int(client_answer) < 18:
                raise ClientError(texts.UNDER_18_DISSCLAIMER)
            return client_answer

        client_conversation.add_question(ConversationQuestion(
            question_key="age",
            question_text="Сколько вам лет? (напишите цифрами, например 21)",
            answer_callback=age_question_callback,
        ))

        # city
        client_conversation.add_question(ConversationQuestion(
            question_key="city",
            question_text="Город проживания? Из какого вы города?",
        ))

        # pr_type
        client_conversation.add_question(ConversationQuestion(
            question_key="pr_type",
            question_text="Какая у вас проблема? Выберите из списка",
            answer_options=texts.PROBLEM_TYPES_MAPPED,
        ))

        # pr_descr
        client_conversation.add_question(ConversationQuestion(
            question_key="pr_descr",
            question_text="Развернуто опишите вашу проблему, это поможет нам лучше подобрать психолога."
                        " Если вы оставите поле пустым  - мы не сможем вам помочь",
        ))

        client_conversation.add_ending_message(texts.END_QUERY)
        return client_conversation

    @staticmethod
    def create_client_from_answers(chat_id: int, answers: dict) -> ClientModel:
        return ClientModel(
            chat_id=chat_id,
            date=datetime.now(),
            **answers,
        )


class PsychologistModel(Base):
    __tablename__ = "psychologists"

    chat_id = sqlalchemy.Column(types.BigInteger)
    name = sqlalchemy.Column(types.Text)
    username = sqlalchemy.Column(types.Text, primary_key=True)
    problem_type = sqlalchemy.Column(types.Text)
    client_sex = sqlalchemy.Column(types.Enum("boy", "girl", "boygirl", name="client_sex"))
    client_lang = sqlalchemy.Column(types.Enum("ru", "kz", "rukz", name="client_lang"))

    @staticmethod
    def create_psychologist_conversation() -> Conversation:
        ps_conversation = Conversation()
        ps_conversation.add_initial_message("Здравствуйте! Сейчас я вас зарегистрирую как нового психолога")

        # name
        ps_conversation.add_question(ConversationQuestion(
            question_key="name",
            question_text="Как вас зовут?"
        ))

        # client_lang
        client_lang_options = [
            ("Русский", "ru"),
            ("Казахский", "kz"),
            ("Оба", "rukz"),
        ]
        ps_conversation.add_question(ConversationQuestion(
            question_key="client_lang",
            question_text="На каком языке вы можете вести консультации?",
            answer_options=client_lang_options,
        ))

        # client_sex
        client_sex_options = [
            ("Мужчины", "boy"),
            ("Женщины", "girl"),
            ("Мужчины и женщины", "boygirl"),
        ]
        ps_conversation.add_question(ConversationQuestion(
            question_key="client_sex",
            question_text="С кем вы можете вести консультации?",
            answer_options=client_sex_options,
        ))

        # pr_types
        def type_from_answer(response: str) -> str:
            try:
                chosen_types = set(response.split(' '))
                return " ".join(x[1] for x in list(filter(lambda x: str(int(x[1]) + 1) in chosen_types, texts.PROBLEM_TYPES_MAPPED)))
            except Exception:
                raise FormatError("Вы ввели номера неправильно")

        ps_conversation.add_question(ConversationQuestion(
            question_key="problem_type",
            question_text="Укажите номера проблем, с которыми вы работаете, из списка ниже (укажите номера через пробел, например, 1 4 9 11):\n" +\
                          "\n".join(f"{idx + 1}) {pr_type}" for idx, pr_type in enumerate(texts.PROBLEM_TYPES_STR)),
            answer_callback=type_from_answer,
        ))

        ps_conversation.add_ending_message("Регистрация завершена")

        return ps_conversation

    @staticmethod
    def create_pyschologist_from_answers(chat_id: int, username: int, answers: dict) -> PsychologistModel:
        return PsychologistModel(chat_id=chat_id, username=username, **answers)


class AssignmentsModel(Base):
    __tablename__ = "assignments"

    client_chat_id = sqlalchemy.Column(types.BigInteger)
    ps_chat_id = sqlalchemy.Column(types.BigInteger, primary_key=True)
    message_id = sqlalchemy.Column(types.BigInteger, primary_key=True)


class AdminModel(Base):
    __tablename__ = "admins"

    admin_chat_id = sqlalchemy.Column(types.BigInteger, primary_key=True)


class DatabaseConnector:
    def __init__(self, db_recipe: str):
        self._db_engine: sqlalchemy.engine.Engine = create_engine(db_recipe, client_encoding='utf8')
        Base.metadata.create_all(self._db_engine)
        self._session_factory = sessionmaker(self._db_engine)

        with self._session_factory() as session:
            session.query(ClientModel).delete()

    def merge_row(self, row: Union[ClientModel, PsychologistModel, AssignmentsModel, AdminModel]):
        with self._session_factory() as session:
            session.merge(row)
            session.commit()

    def list_clients(self) -> list[ClientModel]:
        with self._session_factory() as session:
            return session.query(ClientModel).all()

    def list_psychologists(self) -> list[PsychologistModel]:
        with self._session_factory() as session:
            return session.query(PsychologistModel).all()

    def lookup_psychologists_by_chat(self, chat_id: int) -> PsychologistModel:
        with self._session_factory() as session:
            return session.query(PsychologistModel).filter(PsychologistModel.chat_id == chat_id).one()

    def lookup_psychologists(self, lang: str, sex: str, pr_type: str) -> list[PsychologistModel]:
        with self._session_factory() as session:
            return session.query(PsychologistModel).filter(
                expression.or_(
                    PsychologistModel.client_sex == sex,
                    PsychologistModel.client_sex == "both",
                ),
                expression.or_(
                    PsychologistModel.client_lang == lang,
                    PsychologistModel.client_lang == "both",
                ),
                PsychologistModel.problem_type == pr_type,
            ).all()

    def get_ps_chat_ids(self) -> set[int]:
        with self._session_factory() as session:
            return set(item[0] for item in session.query(PsychologistModel.chat_id).group_by(PsychologistModel.chat_id).all())

    def get_ps_usernames(self) -> set[int]:
        with self._session_factory() as session:
            return set(item[0] for item in session.query(PsychologistModel.username).all())

    def lookup_assignment_info(self, ps_chat_id: int, message_id: int) -> Optional[AssignmentsModel]:
        with self._session_factory() as session:
            return session.query(AssignmentsModel).filter(
                AssignmentsModel.ps_chat_id == ps_chat_id,
                AssignmentsModel.message_id == message_id,
            ).one_or_none()

    def lookup_assignment_info_by_client(self, client_id: int) -> Optional[AssignmentsModel]:
        with self._session_factory() as session:
            return session.query(AssignmentsModel).filter(
                AssignmentsModel.client_chat_id == client_id
            ).one_or_none()

    def remove_client_assignment_infos(self, client_chat_id: int, ps_chat_id_to_leave: Optional[int] = None):
        with self._session_factory() as session:
            if ps_chat_id_to_leave is not None:
                session.query(AssignmentsModel).filter(
                    AssignmentsModel.client_chat_id == client_chat_id,
                    AssignmentsModel.ps_chat_id != ps_chat_id_to_leave,
                ).delete()
            else:
                session.query(AssignmentsModel).filter(
                    AssignmentsModel.client_chat_id == client_chat_id,
                ).delete()
            session.commit()

    def lookup_client(self, client_chat_id: int) -> Optional[ClientModel]:
        with self._session_factory() as session:
            return session.query(ClientModel).filter(
                ClientModel.chat_id == client_chat_id,
            ).one_or_none()

    def list_admins(self) -> list[AdminModel]:
        with self._session_factory() as session:
            return session.query(AdminModel).all()
