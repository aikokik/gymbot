# src/llm_handler.py
from collections import defaultdict, deque
from datetime import timedelta
import json
import logging

from openai import OpenAI

from configs.config import Configs
from src.models._types import (
    Difficulty,
    Exercise,
    MuscleGroup,
    UserId,
    UserProfile,
    WorkoutExercise,
    WorkoutGoal,
    WorkoutPlan,
)


logger = logging.getLogger(__name__)


class GPTAgent:

    def __init__(
        self, system_promt: str, keep_conversation_context: bool = True
    ) -> None:
        logger.info(
            f"Initializing GPTAgent with keep_context={keep_conversation_context}"
        )
        self.__system_promt = system_promt
        self.__keep_conversation_context = keep_conversation_context
        self.client = OpenAI(**vars(Configs().openai))
        # Use deque with maxlen for automatic length management
        self.conversation_context: dict[UserId, deque] = defaultdict(
            lambda: deque(maxlen=5)
        )
        logger.debug(f"System prompt set to: {system_promt}")

    def reset_memory(self, user_id: UserId) -> None:
        """Clear all conversation context for all users."""
        self.conversation_context[user_id].clear()

    async def get_response(
        self,
        user_id: UserId,
        user_message: str,
        model: str = "gpt-3.5-turbo",
        **kwargs: dict,
    ) -> str:
        logger.debug(f"Getting response for user {user_id}")
        logger.debug(f"User message: {user_message}")
        logger.debug(f"Model: {model}, kwargs: {kwargs}")

        # Messages are automatically limited by deque
        self.conversation_context[user_id].append(
            {"role": "user", "content": user_message}
        )
        params = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.__system_promt},
                *self.conversation_context[user_id],
            ],
            "max_tokens": kwargs.get("max_tokens", 500),
            "temperature": kwargs.get("temperature", 0.7),
        }

        try:
            logger.debug(f"Sending request to OpenAI with params: {params}")
            # Get response from OpenAI
            response = self.client.chat.completions.create(**params)
            # Extract response text from the message content
            assistant_message = response.choices[0].message.content
            logger.debug(f"Received response: {assistant_message[:200]}...")

            # Add assistant response to context
            if self.__keep_conversation_context:
                self.conversation_context[user_id].append(
                    {"role": "assistant", "content": assistant_message}
                )
                logger.debug(
                    f"Context length for user {user_id}: {len(self.conversation_context[user_id])}"
                )

            return assistant_message

        except Exception as e:
            logger.error(f"Error getting response from OpenAI: {str(e)}", exc_info=True)
            raise  # Re-raise the exception to handle it in the calling function


PROMTS: dict[str, str] = {
    "fitness_trainer_prompt": (
        "You are a professional fitness trainer creating personalized workout plans."
    ),
    "user_profiler_promt": (
        "You are a fitness profile parser. "
        "Extract information accurately and return only the JSON."
    ),
}


class WorkoutPlannerHandler:
    def __init__(self) -> None:
        logger.info("Initializing WorkoutPlannerHandler")
        self.__fitness_trainer_model = GPTAgent(
            system_promt=PROMTS["fitness_trainer_prompt"]
        )
        self.__user_profiler_model = GPTAgent(
            system_promt=PROMTS["user_profiler_promt"], keep_conversation_context=False
        )

    def reset_memory(self, user_id: UserId) -> None:
        logger.info(f"Resetting memory for user {user_id}")
        self.__fitness_trainer_model.reset_memory(user_id)
        self.__user_profiler_model.reset_memory(user_id)

    async def parse_user_profile(
        self, user_id: UserId, user_message: str
    ) -> UserProfile:
        logger.info(f"Parsing user profile for user {user_id}")
        logger.debug(f"Raw user message: {user_message}")

        prompt = f"""
        Parse the following user text into a structured profile. Extract only the mentioned information.
        User text: {user_message}
        Respond in this exact JSON format:
        {{
            "fitness_level": "beginner/intermediate/advanced",
            "goals": ["strength/weight_loss/muscle_gain/endurance/flexibility", ...],
            "available_equipment": ["equipment1", "equipment2", ...],
            "workout_duration_minutes": number,
            "workout_days": number,
            "medical_limitations": ["limitation1", "limitation2"] or null,
            "additional_info": "string" or null
        }}
        """

        try:
            logger.debug("Sending profile parsing request to LLM")
            response_text = await self.__user_profiler_model.get_response(
                user_id, prompt
            )
            logger.info(f"Received response: {response_text}")

            profile_data = json.loads(response_text)
            logger.debug(f"Parsed profile data: {profile_data}")
            profile = UserProfile(
                fitness_level=Difficulty(profile_data["fitness_level"].lower()),
                goals=[WorkoutGoal(goal.lower()) for goal in profile_data["goals"]],
                available_equipment=[
                    eq.lower() for eq in profile_data["available_equipment"]
                ],
                preferred_workout_duration=timedelta(
                    minutes=profile_data["workout_duration_minutes"]
                ),
                workout_days_per_week=profile_data["workout_days"],
                medical_limitations=profile_data["medical_limitations"],
                additional_info=profile_data["additional_info"],
            )
            logger.info(f"Successfully created user profile for user {user_id}")
            return profile

        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to parse JSON response for user {user_id}: {str(e)}",
                exc_info=True,
            )
            raise ValueError("Invalid response format from LLM") from e
        except Exception as e:
            logger.error(
                f"Error parsing user profile for user {user_id}: {str(e)}",
                exc_info=True,
            )
            raise ValueError("Could not parse user profile. Please try again.") from e

    async def create_workout_plan(
        self, user_id: UserId, user_profile: UserProfile
    ) -> WorkoutPlan:
        logger.info(f"Creating workout plan for user {user_id}")
        logger.debug(f"User profile: {user_profile}")

        prompt = f"""Create a personalized workout plan with the following requirements:
                    User Profile:
                    - Fitness Level: {user_profile.fitness_level}
                    - Goals: {', '.join(user_profile.goals)}
                    - Available Equipment: {', '.join(user_profile.available_equipment)}
                    - Preferred Workout Duration: {user_profile.preferred_workout_duration}
                    - Workout Days Per Week: {user_profile.workout_days_per_week}
                    - Medical Limitations: {', '.join(user_profile.medical_limitations or [])}
                    - Additional Info: {user_profile.additional_info}
                    Use only the equipment that the user has available.
                    For the muscle group, use only one of "chest/back/legs/shoulders/arms/core/full_body"
                    For the difficulty, use only one of "beginner/intermediate/advanced".
                    Return ONLY raw JSON with no markdown formatting or code blocks. The response must be valid JSON that follows this exact schema:
                    {{
                        "weekly_schedule": [
                            {{
                                "day": 1,
                                "focus": "string",
                                "exercises": [
                                    {{
                                        "name": "exercise-name",
                                        "description": "exercise-description",
                                        "muscle_group": "chest/back/legs/shoulders/arms/core/full_body",
                                        "difficulty": "beginner/intermediate/advanced",
                                        "equipment": "equipment-type",
                                        "instructions": ["step1", "step2"],
                                        "duration_minutes": number,
                                        "sets": number,
                                        "reps": number,
                                        "rest_seconds": number,
                                        "video_url": "string" or null,
                                        "image_url": "string" or null,
                                        "notes": "string" or null
                                    }}
                                ]
                            }}
                        ],
                        "notes": "string"
                    }}
        """
        try:
            logger.debug("Sending workout plan creation request to LLM")
            response = await self.__fitness_trainer_model.get_response(
                user_id, prompt, max_tokens=1500
            )
            logger.info(f"Received response: {response}")

            # Parse the response string directly
            plan_data = json.loads(response)
            logger.info(f"Parsed plan data: {plan_data}")

            workouts = []
            for day in plan_data["weekly_schedule"]:
                day_exercises = []
                for ex in day["exercises"]:
                    exercise = Exercise(
                        name=ex["name"],
                        description=ex["description"],
                        muscle_group=MuscleGroup(ex["muscle_group"].lower()),
                        difficulty=Difficulty(ex["difficulty"].lower()),
                        equipment=ex["equipment"],
                        instructions=ex["instructions"],
                        video_url=ex["video_url"],
                        image_url=ex["image_url"],
                        sets_default=ex["sets"],
                        reps_default=ex["reps"],
                    )
                    workout_exercise = WorkoutExercise(
                        exercise=exercise,
                        sets=ex["sets"],
                        reps=ex["reps"],
                        rest_between_sets=ex["rest_seconds"],
                        notes=ex.get("notes"),
                    )
                    day_exercises.append(workout_exercise)
                workouts.append(day_exercises)

            return WorkoutPlan(
                user_profile=user_profile,
                duration_weeks=4,  # Default to 4-week plan
                workouts=workouts,
                notes=plan_data["notes"],
            )

        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to parse JSON response for user {user_id}: {str(e)}",
                exc_info=True,
            )
            return self._create_fallback_workout_plan(user_profile)
        except Exception as e:
            logger.error(
                f"Error creating workout plan for user {user_id}: {str(e)}",
                exc_info=True,
            )
            return self._create_fallback_workout_plan(user_profile)

    def _create_fallback_workout_plan(self, user_profile: UserProfile) -> WorkoutPlan:
        """Create a basic fallback workout plan when LLM fails."""

        # Day 1 Exercises
        day1_exercises = [
            WorkoutExercise(
                exercise=Exercise(
                    name="Dumbbell Squats",
                    description="Basic compound exercise for lower body strength",
                    instructions=[
                        "Hold dumbbells by your sides",
                        "Squat down with proper form",
                    ],
                    muscle_group=MuscleGroup.LEGS,
                    difficulty=Difficulty.BEGINNER,
                    equipment="dumbbell",
                    video_url=None,
                    image_url=None,
                    sets_default=3,
                    reps_default=12,
                    duration_minutes=None,
                ),
                sets=3,
                reps=12,
                rest_between_sets=60,
                notes="Keep your back straight and chest up",
            ),
            WorkoutExercise(
                exercise=Exercise(
                    name="Dumbbell Chest Press",
                    description="Basic chest exercise for upper body strength",
                    instructions=["Lie on bench", "Press dumbbells up with control"],
                    muscle_group=MuscleGroup.CHEST,
                    difficulty=Difficulty.BEGINNER,
                    equipment="dumbbell",
                    video_url=None,
                    image_url=None,
                    sets_default=3,
                    reps_default=12,
                    duration_minutes=None,
                ),
                sets=3,
                reps=12,
                rest_between_sets=60,
                notes="Keep core engaged throughout movement",
            ),
        ]

        # Day 2 Exercises
        day2_exercises = [
            WorkoutExercise(
                exercise=Exercise(
                    name="Dumbbell Rows",
                    description="Back strengthening exercise",
                    instructions=[
                        "Bend over with flat back",
                        "Pull dumbbells to sides",
                    ],
                    muscle_group=MuscleGroup.BACK,
                    difficulty=Difficulty.BEGINNER,
                    equipment="dumbbell",
                    video_url=None,
                    image_url=None,
                    sets_default=3,
                    reps_default=12,
                    duration_minutes=None,
                ),
                sets=3,
                reps=12,
                rest_between_sets=60,
                notes="Keep back straight throughout movement",
            ),
            WorkoutExercise(
                exercise=Exercise(
                    name="Core Plank",
                    description="Core stability exercise",
                    instructions=["Hold plank position", "Keep body straight"],
                    muscle_group=MuscleGroup.CORE,
                    difficulty=Difficulty.BEGINNER,
                    equipment="bodyweight",
                    video_url=None,
                    image_url=None,
                    sets_default=3,
                    reps_default=30,
                    duration_minutes=1,
                ),
                sets=3,
                reps=30,
                rest_between_sets=60,
                notes="Maintain proper form throughout hold",
            ),
        ]

        # Day 3 Exercises
        day3_exercises = [
            WorkoutExercise(
                exercise=Exercise(
                    name="Shoulder Press",
                    description="Shoulder strengthening exercise",
                    instructions=["Press dumbbells overhead", "Control the descent"],
                    muscle_group=MuscleGroup.SHOULDERS,
                    difficulty=Difficulty.BEGINNER,
                    equipment="dumbbell",
                    video_url=None,
                    image_url=None,
                    sets_default=3,
                    reps_default=12,
                    duration_minutes=None,
                ),
                sets=3,
                reps=12,
                rest_between_sets=60,
                notes="Keep core engaged and avoid arching back",
            ),
            WorkoutExercise(
                exercise=Exercise(
                    name="Bicep Curls",
                    description="Arm isolation exercise",
                    instructions=["Curl dumbbells up", "Lower with control"],
                    muscle_group=MuscleGroup.ARMS,
                    difficulty=Difficulty.BEGINNER,
                    equipment="dumbbell",
                    video_url=None,
                    image_url=None,
                    sets_default=3,
                    reps_default=12,
                    duration_minutes=None,
                ),
                sets=3,
                reps=12,
                rest_between_sets=60,
                notes="Keep elbows close to body",
            ),
        ]

        # Create the complete workout plan
        return WorkoutPlan(
            user_profile=user_profile,
            workouts=[day1_exercises, day2_exercises, day3_exercises],
            duration_weeks=4,
            notes="Start with lighter weights to focus on form. Increase weight gradually as you get comfortable with the movements.",
        )
