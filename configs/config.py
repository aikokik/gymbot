# src/config.py
from dataclasses import dataclass
import os

from dotenv import load_dotenv


# Load environment variables
load_dotenv()


@dataclass
class IntergaceConfig:
    api_key: str | None


@dataclass
class HandlerConfig:
    api_key: str | None


@dataclass
class CalendarConfig:
    calendar_id: str
    timezone: str
    default_reminder_minutes: tuple[int, ...]
    default_days_ahead: int


class TelegramBot(IntergaceConfig):
    def __init__(self) -> None:
        self.api_key = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")


class OpenAI(HandlerConfig):
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")


class GoogleCalendar(CalendarConfig):
    def __init__(self) -> None:
        self.calendar_id = "primary"
        self.timezone = "UTC"
        self.default_reminder_minutes = (30, 10)
        self.default_days_ahead = 7


@dataclass
class Configs:
    telegram = TelegramBot()
    openai = OpenAI()
    google_calendar = GoogleCalendar()
