# src/tools/calendar/calendar_manager.py
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import time
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
        self._user_locks: dict[int, tuple[Lock, float]] = {}
        self._operation_lock = Lock()
        self._cleanup_threshold = 3600

    def _get_user_lock(self, user_id: int) -> Lock:
        """Get or create a lock for a specific user."""
        current_time = time()

        with self._operation_lock:
            # todo(aidana) there is needed scheduler that will clean locks
            self._cleanup_old_locks(current_time)
            if user_id not in self._user_locks:
                self._user_locks[user_id] = (Lock(), current_time)
            else:
                # Update last used time
                lock, _ = self._user_locks[user_id]
                self._user_locks[user_id] = (lock, current_time)

            return self._user_locks[user_id][0]

    def _cleanup_old_locks(self, current_time: float) -> None:
        """Remove locks that haven't been used for a while."""
        to_remove = []
        for user_id, (_, last_used) in self._user_locks.items():
            if current_time - last_used > self._cleanup_threshold:
                to_remove.append(user_id)

        for user_id in to_remove:
            del self._user_locks[user_id]
            logger.debug(f"Cleaned up lock for user {user_id}")

    def _create_event_body(
        self,
        start_time: datetime,
        end_time: datetime,
        workout_exercises: list[WorkoutExercise],
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
            "description": self._format_workout_description(workout_exercises),
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
        self, user_id: int, workout_times: list[TimeSlot], workout_plan: WorkoutPlan
    ) -> list[str]:
        """
        Create calendar events for workouts with concurrency control.

        Args:
            user_id: Telegram user ID
            workout_times: list of workout time slots
            workout_plan: Workout plan details

        Returns:
            list of created event IDs

        Raises:
            HttpError: If calendar API request fails
        """
        assert len(workout_times) == len(workout_plan.workouts)
        event_ids: list[str] = []

        user_lock = self._get_user_lock(user_id)

        try:
            with user_lock:
                for index, workout in enumerate(workout_times):
                    event = self._create_event_body(
                        workout["start"], workout["end"], workout_plan.workouts[index]
                    )

                    result = (
                        self.service.events()
                        .insert(calendarId=self.config.calendar_id, body=event)
                        .execute()
                    )

                    event_ids.append(result["id"])

        except Exception as e:
            # Rollback: delete any events that were created
            with user_lock:
                for event_id in event_ids:
                    try:
                        self.service.events().delete(
                            calendarId=self.config.calendar_id, eventId=event_id
                        ).execute()
                    except Exception as delete_error:
                        logger.error(f"Error during rollback: {delete_error}")

            logger.error(f"Error creating calendar events: {e}")
            raise

        return event_ids

    def _format_workout_description(
        self, workout_exercises: list[WorkoutExercise]
    ) -> str:
        description_parts = ["Today's Workout:\n"]

        for exercise in workout_exercises:
            description_parts.extend(
                [
                    f"• {exercise.exercise.name}",
                    f"  - {exercise.sets} sets of {exercise.reps} reps",
                    f"  - Rest: {exercise.rest_between_sets} seconds\n",
                    f"  - Equipment: {exercise.exercise.equipment}\n"
                    f"  - Instructions: {' '.join(exercise.exercise.instructions)}\n"
                    f"  - Reference to image : {exercise.exercise.image_url}\n"
                    f"  - Reference to video : {exercise.exercise.video_url}\n"
                    f"  - Difficulty: {exercise.exercise.difficulty}\n",
                ]
            )

        return "\n".join(description_parts)

    async def suggest_workout_times(
        self,
        user_id: int,
        preferred_times: list[TimeSlot],
        days_ahead: int | None = None,
    ) -> list[TimeSlot]:
        """
        Suggest workout times with concurrency control.

        Args:
            user_id: Telegram user ID
            preferred_times: List of preferred time slots
            days_ahead: Number of days to look ahead
        """
        days_ahead = days_ahead or self.config.default_days_ahead
        suggested_times: list[TimeSlot] = []

        # Get user-specific lock
        user_lock = self._get_user_lock(user_id)

        try:
            with user_lock:
                now = datetime.now(timezone.utc)
                week_later = now + timedelta(days=days_ahead)

                time_min = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                time_max = week_later.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

                logger.info(f"Fetching events between {time_min} and {time_max}")

                events_result = (
                    self.service.events()
                    .list(
                        calendarId=self.config.calendar_id,
                        timeMin=time_min,
                        timeMax=time_max,
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
                    end_time = pref["end"]

                    if self._is_time_slot_available(start_time, end_time, busy_times):
                        suggested_times.append({"start": start_time, "end": end_time})

            return suggested_times

        except HttpError as e:
            logger.error(f"An error occurred: {e}")
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
        # Ensure all datetimes are timezone-aware
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        return not any(
            start < busy_end and end > busy_start for busy_start, busy_end in busy_times
        )
