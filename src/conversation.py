from typing import Optional, Callable, Iterable, Any
from dataclasses import dataclass
from telebot.types import Chat


class FormatError(Exception):
    # User entered answer in a wrong format
    pass

class ClientError(Exception):
    # User cannot be arranged
    pass


@dataclass
class ConversationQuestion:
    question_key: str
    question_text: str
    answer_callback: Optional[Callable[[Chat], Any]] = None
    answer_options: Optional[Iterable[tuple[str, str]]] = None


class Conversation:
    __slots__ = [
        "_conversation",
        "_initial_message",
        "_ending_message",
    ]

    def __init__(self):
        self._conversation: list[ConversationQuestion] = list()
        self._initial_message: Optional[str] = None
        self._ending_message: Optional[str] = None

    def add_question(self, question: ConversationQuestion):
        self._conversation.append(question)

    def add_initial_message(self, message: str):
        self._initial_message = message

    def add_ending_message(self, message: str):
        self._ending_message = message

    @property
    def conversation(self) -> list[ConversationQuestion]:
        return self._conversation

    @property
    def initial_message(self) -> Optional[str]:
        return self._initial_message

    @property
    def ending_message(self) -> Optional[str]:
        return self._ending_message
