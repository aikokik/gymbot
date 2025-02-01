# src/tools/calendar/calendar_manager.py
from datetime import datetime, timedelta, timezone
from typing import TypedDict
import logging

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from configs.config import CalendarConfig
from src.models._types import WorkoutExercise, WorkoutPlan


logger = logging.getLogger(__name__)


class TimeSlot(TypedDict):
    start: datetime
    end: datetime


class CalendarEvent(TypedDict):
    summary: str
    description: str
    start: dict[str, str]
    end: dict[str, str]
    reminders: dict[str, object]


class CalendarManager:
    """Manages Google Calendar operations for workout scheduling."""

    def __init__(self, credentials: Credentials, config: CalendarConfig) -> None:
        """
        Initialize Calendar Manager.

        Args:
            credentials: Google OAuth2 credentials
        """
        self.service: Resource = build("calendar", "v3", credentials=credentials)
        self.config = config

    def _create_event_body(
        self, start_time: datetime, end_time: datetime, workout_plan: WorkoutPlan
    ) -> CalendarEvent:
        """
        Create calendar event body with workout details.

        Args:
            start_time: Event start time
            end_time: Event end time
            workout_plan: Workout plan details

        Returns:
            Formatted calendar event body
        """
        return {
            "summary": "Workout Session 💪",
            "description": self._format_workout_description(workout_plan.workouts),
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": self.config.timezone,
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": self.config.timezone,
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": mins}
                    for mins in self.config.default_reminder_minutes
                ],
            },
        }

    async def create_workout_events(
        self, workout_times: list[TimeSlot], workout_plan: WorkoutPlan
    ) -> list[str]:
        """
        Create calendar events for workouts.

        Args:
            workout_times: list of workout time slots
            workout_plan: Workout plan details

        Returns:
            list of created event IDs

        Raises:
            HttpError: If calendar API request fails
        """
        event_ids: list[str] = []

        for workout in workout_times:
            try:
                event = self._create_event_body(
                    workout["start"], workout["end"], workout_plan
                )

                result = (
                    self.service.events()
                    .insert(calendarId=self.config.CALENDAR_ID, body=event)
                    .execute()
                )

                event_ids.append(result["id"])

            except HttpError as e:
                logger.error(f"Error creating calendar event: {e.reason}")
                raise
            except ValueError as e:
                logger.error(f"Invalid data format in calendar event: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error creating calendar event: {e}")
                raise

        return event_ids

    def _format_workout_description(self, workouts: list[WorkoutExercise]) -> str:
        """
        Format workout details for calendar description.

        Args:
            workouts: list of workout exercises

        Returns:
            Formatted workout description
        """
        description_parts = ["Today's Workout:\n"]

        for workout in workouts:
            description_parts.extend(
                [
                    f"• {workout.exercise.name}",
                    f"  - {workout.sets} sets of {workout.reps} reps",
                    f"  - Rest: {workout.rest_between_sets} seconds\n",
                    f"  - Equipment: {workout.exercise.equipment}\n"
                    f"  - Instructions: {' '.join(workout.exercise.instructions)}\n"
                    f"  - Reference to image : {workout.exercise.image_url}\n"
                    f"  - Reference to video : {workout.exercise.video_url}\n"
                    f"  - Difficulty: {workout.exercise.difficulty}\n",
                ]
            )

        return "\n".join(description_parts)

    async def suggest_workout_times(
        self,
        preferred_times: list[TimeSlot],
        duration_minutes: int,
        days_ahead: int | None = None,
    ) -> list[TimeSlot]:
        """
        Suggest available workout times based on calendar.

        Args:
            preferred_times: list of preferred time slots
            duration_minutes: Duration of workout
            days_ahead: Number of days to look ahead

        Returns:
            list of available time slots

        Raises:
            HttpError: If calendar API request fails
        """
        days_ahead = days_ahead or self.config.DEFAULT_DAYS_AHEAD
        suggested_times: list[TimeSlot] = []

        now = datetime.now(timezone.utc)
        week_from_now = now + timedelta(days=days_ahead)

        try:
            events_result = (
                self.service.events()
                .list(
                    calendarId=self.config.CALENDAR_ID,
                    timeMin=now.isoformat() + "Z",
                    timeMax=week_from_now.isoformat() + "Z",
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            busy_times = [
                (
                    datetime.fromisoformat(
                        event["start"].get("dateTime", event["start"].get("date"))
                    ),
                    datetime.fromisoformat(
                        event["end"].get("dateTime", event["end"].get("date"))
                    ),
                )
                for event in events_result.get("items", [])
            ]

            for pref in preferred_times:
                start_time = pref["start"]
                end_time = start_time + timedelta(minutes=duration_minutes)

                if self._is_time_slot_available(start_time, end_time, busy_times):
                    suggested_times.append({"start": start_time, "end": end_time})

            return suggested_times

        except HttpError as e:
            logger.error(f"Error fetching calendar events: {e.reason}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error suggesting workout times: {e}")
            raise

    def _is_time_slot_available(
        self,
        start: datetime,
        end: datetime,
        busy_times: list[tuple[datetime, datetime]],
    ) -> bool:
        """
        Check if a time slot is available.

        Args:
            start: Start time to check
            end: End time to check
            busy_times: list of busy time periods

        Returns:
            True if time slot is available
        """
        return not any(
            start < busy_end and end > busy_start for busy_start, busy_end in busy_times
        )
