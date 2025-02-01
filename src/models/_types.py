# src/exercises/exercise_types.py
from datetime import timedelta
from enum import Enum
from typing import NewType

from pydantic import BaseModel


UserId = NewType("UserId", int)


class Difficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class WorkoutGoal(str):
    STRENGTH = "strength"
    WEIGHT_LOSS = "weight_loss"
    MUSCLE_GAIN = "muscle_gain"
    ENDURANCE = "endurance"
    FLEXIBILITY = "flexibility"


class UserProfile(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    fitness_level: Difficulty
    goals: list[WorkoutGoal]
    available_equipment: list[str]
    preferred_workout_duration: timedelta
    workout_days_per_week: int
    medical_limitations: list[str] | None
    additional_info: str | None


class MuscleGroup(str, Enum):
    CHEST = "chest"
    BACK = "back"
    LEGS = "legs"
    SHOULDERS = "shoulders"
    ARMS = "arms"
    CORE = "core"
    FULL_BODY = "full_body"


class Exercise(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str
    muscle_group: MuscleGroup
    difficulty: Difficulty
    equipment: str
    video_url: str | None
    image_url: str | None
    instructions: list[str]
    duration_minutes: int | None = None
    sets_default: int | None
    reps_default: int | None


class WorkoutExercise(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    exercise: Exercise
    sets: int
    reps: int
    rest_between_sets: int  # seconds
    notes: str | None


class WorkoutPlan(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    user_profile: UserProfile
    duration_weeks: int
    workouts: list[list[WorkoutExercise]]  # List of workouts for each day
    notes: str | None
