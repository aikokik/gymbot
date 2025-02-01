from datetime import datetime, timedelta
from typing import List
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from configs.config import Configs
from configs.logging import setup_logging
from src.handlers.handler import WorkoutPlannerHandler
from src.models._types import WorkoutPlan
from src.tools.calendar.auth import CalendarAuth
from src.tools.calendar.calendar_manager import CalendarManager, TimeSlot


# Set up logging
setup_logging(log_dir="logs", app_name="agentic_ai")
logger = logging.getLogger(__name__)
handler = WorkoutPlannerHandler()

# Get token from Interface
telegram_config = Configs().telegram
logger.info("Telegram configuration loaded successfully")


class GymBot:
    def __init__(self) -> None:
        logger.info("Initializing GymBot")
        self.calendar_auth = CalendarAuth()

    # Command handlers
    async def start_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Send a message when the command /start is issued."""
        user = update.effective_user
        logger.info(f"Start command received from user {user.id} ({user.first_name})")
        await update.message.reply_text(
            f"👋 Hi {user.first_name}! I am your Gym Agent Bot.\n"
            f"I can help you create personal training plan through chat.\n"
            f"Click /help to see all available commands."
        )

    async def end_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Clear chat history and send good bye message when the command /end is issued."""
        user = update.effective_user
        logger.info(f"End command received from user {user.id} ({user.first_name})")
        self.reset_conversation_context(user.id)
        # Clear user data
        context.user_data.clear()
        await update.message.reply_text(f"👋 Bye bye {user.first_name}")

    async def error_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Log Errors caused by Updates."""
        logger.error(
            f'Update "{update}" caused error "{context.error}"', exc_info=context.error
        )

    async def start_workout_plan(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Start workout plan creation process"""
        user = update.effective_user
        logger.info(
            f"Starting workout plan creation for user {user.id} ({user.first_name})"
        )
        context.user_data["creating_profile"] = True
        await update.message.reply_text(
            "Let's create your personalized workout plan! 🏋️‍♂️\n\n"
            "Please tell me about yourself, for example:\n\n"
            "1. Fitness Level: beginner/intermediate/advanced\n"
            "2. Fitness Goals: strength/weight loss/muscle gain/endurance/flexibility\n"
            "3. Weekly Schedule: How many days can you workout? (1-7)\n"
            "4. Session Duration: How long can you exercise per session? (minutes)\n"
            "5. Available Equipment: bodyweight/dumbbells/barbell/machine/cables\n"
            "6. Target Areas: any specific muscle groups you want to focus on?\n"
            "7. Medical Limitations: any injuries or conditions I should know about?\n\n"
            "Please add any additional information or preference :)"
        )

    async def handle_profile_creation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        try:
            """Handle workout profile creation conversation"""
            if not context.user_data.get("creating_profile"):
                logger.debug(
                    f"Ignoring message from user {user.id} - not in profile creation mode"
                )
                await update.message.reply_text(
                    "Please use /start_plan to start creating your workout plan."
                )
                return

            logger.info(
                f"Processing profile creation for user {user.id} ({user.first_name})"
            )
            user_profile_in_text = update.message.text.lower()
            logger.debug(f"Raw profile input: {user_profile_in_text}")

            # Get structured data from LLM
            user_profile = await handler.parse_user_profile(
                user.id, user_profile_in_text
            )
            logger.info(
                f"Successfully parsed profile for user {user.id}: {user_profile}"
            )

            context.user_data["user_profile"] = user_profile

            # Format medical limitations
            medical_limitations = (
                "None"
                if not user_profile.medical_limitations
                else ", ".join(user_profile.medical_limitations)
            )

            # Format additional info
            additional_info = (
                "None"
                if not user_profile.additional_info
                else user_profile.additional_info
            )

            context.user_data["creating_profile"] = False  # Clear the flag
            await update.message.reply_text(
                f"Great! I've recorded your profile:\n\n"
                f"• Fitness Level: {user_profile.fitness_level}\n"
                f"• Goals: {', '.join(user_profile.goals)}\n"
                f"• Available Equipment: {', '.join(user_profile.available_equipment)}\n"
                f"• Schedule: {user_profile.workout_days_per_week} days/week\n"
                f"• Duration: {int(user_profile.preferred_workout_duration.total_seconds() / 60)} minutes\n"
                f"• Medical Limitations: {medical_limitations}\n"
                f"• Additional Info: {additional_info}\n\n"
                "Ready to create your workout plan! 💪"
                "/create_plan to start"
            )
        except ValueError as e:
            logger.error(
                f"Profile creation failed for user {user.id}: {str(e)}", exc_info=True
            )
            await update.message.reply_text(
                f"Sorry, I couldn't understand all the details. Could you try again?\n{str(e)}"
            )
        except Exception:
            logger.error(
                f"Unexpected error in profile creation for user {user.id}",
                exc_info=True,
            )
            await update.message.reply_text(
                "Sorry, something went wrong. Please try again later."
            )

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Send a message when the command /help is issued."""
        user = update.effective_user
        logger.info(f"Help command received from user {user.id} ({user.first_name})")

        help_text = (
            "🤖 Available Commands:\n\n"
            "/start - Start the bot and get a welcome message\n"
            "/help - Show this help message\n"
            "/start_plan - Begin creating your personalized workout plan\n"
            "/create_plan - Create your workout plan\n"
            "/end - End the current session and clear chat history\n\n"
            "/connect_calendar - Connect your Google Calendar to schedule workouts\n\n"
            "💡 Tips:\n"
            "• Use /start_plan to create a new workout plan\n"
            "• Follow the prompts and provide detailed information\n"
            "• Use /end when you're done to clear the conversation"
        )

        await update.message.reply_text(help_text)

    def reset_conversation_context(self, user_id: int) -> None:
        """Reset all conversation context for the given user."""
        logger.info(f"Resetting conversation context for user {user_id}")
        try:
            handler.reset_memory(user_id)
        except Exception as e:
            logger.error(
                f"Error resetting context for user {user_id}: {str(e)}", exc_info=True
            )
            raise

    async def create_workout_plan(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Create workout plan"""
        user = update.effective_user
        logger.info(f"Creating workout plan for user {user.id} ({user.first_name})")

        if "user_profile" not in context.user_data:
            await update.message.reply_text(
                "Please create your profile first using /start_plan"
            )
            return

        try:
            plan = await handler.create_workout_plan(
                user.id, context.user_data["user_profile"]
            )
            message_parts = self.format_workout_plan(plan)

            # Send introduction
            await update.message.reply_text(
                "🎉 *Your Personalized Workout Plan is Ready\\!*",
                parse_mode="MarkdownV2",
            )

            # Send each part of the workout plan
            for part in message_parts:
                await update.message.reply_text(
                    part, parse_mode="MarkdownV2", disable_web_page_preview=True
                )

            # Store workout plan for scheduling
            context.user_data["workout_plan"] = plan

            # Send final message
            await update.message.reply_text(
                "To schedule these workouts in your calendar, use /connect\\_calendar",
                parse_mode="MarkdownV2",
            )

        except Exception as e:
            logger.error(f"Error creating workout plan: {str(e)}", exc_info=True)
            await update.message.reply_text(
                "Sorry, there was an error creating your workout plan. Please try again."
            )

    async def request_calendar_auth(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Request calendar authorization"""
        user = update.effective_user
        user_id = user.id
        logger.info(
            f"Calendar authorization requested by user {user_id} ({user.first_name})"
        )

        try:
            # Check if already authenticated
            if self.calendar_auth.get_credentials(user_id):
                await update.message.reply_text(
                    "You're already connected to Google Calendar!"
                    "Now, let's schedule your workouts. When do you prefer to exercise?\n\n"
                    "Please provide your preferred workout time in 24-hour format (HH:MM), e.g., '14:30'"
                )
                return

            await update.message.reply_text(
                "Starting Google Calendar authentication..."
            )
            self.calendar_auth.start_auth_flow(user_id)

            await update.message.reply_text(
                "✅ Successfully connected to Google Calendar! 🎉\n"
                "Now, let's schedule your workouts. When do you prefer to exercise?\n\n"
                "Please provide your preferred workout time in 24-hour format (HH:MM), e.g., '14:30'"
            )

        except Exception as e:
            logger.error(f"Calendar authentication failed for user {user_id}: {str(e)}")
            await update.message.reply_text(
                "Sorry, couldn't complete authorization. Please try again or contact support."
            )

    async def handle_auth_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle OAuth callback with authorization code"""
        user = update.effective_user
        user_id = user.id
        logger.info(f"Received auth callback from user {user_id} ({user.first_name})")

        try:
            auth_code = update.message.text
            logger.debug(f"Processing auth code for user {user_id}")

            if not context.user_data.get("auth_flow"):
                logger.warning(f"No auth flow found for user {user_id}")
                await update.message.reply_text(
                    "Please start the authentication process first with /connect_calendar"
                )
                return

            flow = context.user_data["auth_flow"]
            logger.debug(f"Retrieved auth flow for user {user_id}")

            self.calendar_auth.finish_auth_flow(user_id, flow, auth_code)
            logger.info(
                f"Successfully authenticated user {user_id} with Google Calendar"
            )

            await update.message.reply_text(
                "✅ Successfully connected to Google Calendar! 🎉\n"
                "Now, let's schedule your workouts. When do you prefer to exercise?\n\n"
                "Please provide your preferred workout time in 24-hour format (HH:MM), e.g., '14:30'"
            )

            # Start time preference collection
            logger.debug(f"Started time preference collection for user {user_id}")

        except Exception as e:
            logger.error(
                f"Calendar authentication failed for user {user_id}: {str(e)}",
                exc_info=True,
            )
            await update.message.reply_text(
                "Sorry, couldn't complete authorization. Please try again or contact support."
            )

    async def handle_time_preference(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle user's preferred workout time input."""
        user = update.effective_user
        user_id = user.id
        logger.info(
            f"Processing time preference for user {user_id} ({user.first_name})"
        )

        if "workout_plan" not in context.user_data:
            logger.warning(f"No workout plan found for user {user_id}")
            await update.message.reply_text(
                "Please create a workout plan first using /create_plan"
            )
            return

        try:
            # Validate time format
            time_str = update.message.text.strip()
            logger.debug(f"Received time input from user {user_id}: {time_str}")

            try:
                hour, minute = map(int, time_str.split(":"))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError("Invalid time values")
            except ValueError:
                logger.error(f"Invalid time format from user {user_id}: {time_str}")
                await update.message.reply_text(
                    "⚠️ Please enter time in 24-hour format (HH:MM), e.g., 14:30"
                )
                return

            logger.debug(f"Valid time received: {time_str}")

            # Get calendar credentials
            creds = self.calendar_auth.get_credentials(user_id)
            if not creds:
                logger.error(f"No calendar credentials found for user {user_id}")
                await update.message.reply_text(
                    "Please connect your Google Calendar first using /connect_calendar"
                )
                return

            logger.debug(f"Retrieved calendar credentials for user {user_id}")
            calendar = CalendarManager(creds, config=Configs().google_calendar)

            # Generate preferred times for next 7 days
            now = datetime.now()
            preferred_times = []
            for day in range(7):
                target_date = now.date() + timedelta(days=day)
                target_time = datetime.strptime(time_str, "%H:%M").time()
                preferred_datetime = datetime.combine(target_date, target_time)

                # Skip if time is in the past
                if preferred_datetime > now:
                    preferred_times.append(
                        {
                            "start": preferred_datetime,
                            "end": preferred_datetime + timedelta(minutes=60),
                        }
                    )

            logger.debug(f"Generated {len(preferred_times)} preferred time slots")

            # Get suggested times
            suggested_times = await calendar.suggest_workout_times(
                preferred_times, duration_minutes=60
            )

            if not suggested_times:
                logger.info(f"No available time slots found for user {user_id}")
                await update.message.reply_text(
                    "❌ No available time slots found for the next week.\n"
                    "Please try a different time."
                )
                return

            # Store suggested times for confirmation
            context.user_data["suggested_times"] = suggested_times
            context.user_data["awaiting_time_confirmation"] = True

            await self._send_time_confirmation(update, context, suggested_times)

        except Exception as e:
            logger.error(
                f"Error processing time preference for user {user_id}: {str(e)}",
                exc_info=True,
            )
            await update.message.reply_text(
                "Sorry, something went wrong. Please try again or contact support."
            )

    async def handle_time_confirmation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle user's confirmation of suggested workout times."""
        user_id = update.effective_user.id
        logger.debug(f"Processing time confirmation for user {user_id}")

        if not context.user_data.get("awaiting_time_confirmation"):
            logger.warning(f"Unexpected time confirmation from user {user_id}")
            await update.message.reply_text(
                "Please start over with setting your preferred time."
            )
            return

        try:
            # Parse and validate selected indices
            selection = update.message.text.strip()
            try:
                selected_indices = [int(i.strip()) - 1 for i in selection.split(",")]
                suggested_times = context.user_data["suggested_times"]

                if not all(0 <= i < len(suggested_times) for i in selected_indices):
                    raise ValueError("Invalid selection index")

                selected_times = [suggested_times[i] for i in selected_indices]

            except (ValueError, IndexError):
                logger.error(f"Invalid time selection from user {user_id}: {selection}")
                await update.message.reply_text(
                    "⚠️ Please enter valid numbers separated by commas (e.g., 1,2,3)"
                )
                return

            logger.debug(f"Selected {len(selected_times)} time slots")

            # Get calendar manager
            creds = self.calendar_auth.get_credentials(user_id)
            if not creds:
                logger.error(f"No calendar credentials found for user {user_id}")
                await update.message.reply_text(
                    "Please connect your Google Calendar first using /connect"
                )
                return

            calendar = CalendarManager(creds)

            # Create workout events
            workout_plan = context.user_data.get("workout_plan")
            if not workout_plan:
                logger.error(f"No workout plan found for user {user_id}")
                await update.message.reply_text(
                    "Sorry, your workout plan was not found. Please start over."
                )
                return

            logger.debug("Creating calendar events...")
            event_ids = await calendar.create_workout_events(
                selected_times, workout_plan
            )

            logger.info(f"Created {len(event_ids)} calendar events for user {user_id}")
            await update.message.reply_text(
                f"✅ Successfully scheduled {len(event_ids)} workout sessions!\n"
                "Check your Google Calendar for details."
            )

            # Clear confirmation state
            context.user_data["awaiting_time_confirmation"] = False
            context.user_data.pop("suggested_times", None)

        except Exception as e:
            logger.error(
                f"Failed to create calendar events for user {user_id}: {str(e)}"
            )
            await update.message.reply_text(
                "Sorry, couldn't schedule the workouts. Please try again or contact support."
            )

    async def _send_time_confirmation(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        suggested_times: List[TimeSlot],
    ) -> None:
        """Send time confirmation message with suggested slots."""
        time_options = []
        for i, slot in enumerate(suggested_times, 1):
            start_time = slot["start"].strftime("%Y-%m-%d %H:%M")
            time_options.append(f"{i}. {start_time}")

        message = (
            "🕒 Available time slots:\n\n"
            f"{chr(10).join(time_options)}\n\n"
            "Please select time slots by entering their numbers "
            "separated by commas (e.g., 1,3,4)"
        )
        await update.message.reply_text(message)

    def format_workout_plan(self, plan: WorkoutPlan) -> list[str]:
        """Format workout plan into a readable message. Returns a list of message chunks."""

        def escape_markdown(text: str) -> str:
            special_chars = [
                "_",
                "*",
                "[",
                "]",
                "(",
                ")",
                "~",
                "`",
                ">",
                "#",
                "+",
                "-",
                "=",
                "|",
                "{",
                "}",
                ".",
                "!",
            ]
            for char in special_chars:
                text = text.replace(char, f"\\{char}")
            return text

        weeks = plan.duration_weeks
        messages = []
        current_message = [f"🏋️‍♂️ *{escape_markdown(str(weeks))} Week Workout Plan*\n"]

        for week in range(weeks):
            week_header = f"\n*Week {escape_markdown(str(week + 1))}*"

            for day, workout in enumerate(plan.workouts, 1):
                day_parts = [f"\n*Day {escape_markdown(str(day))}*"]

                for exercise in workout:
                    name = escape_markdown(str(exercise.exercise.name))
                    instructions = escape_markdown(
                        str(exercise.exercise.instructions)
                        if isinstance(exercise.exercise.instructions, str)
                        else "; ".join(exercise.exercise.instructions)
                    )
                    notes = escape_markdown(str(exercise.notes))
                    equipment = escape_markdown(str(exercise.exercise.equipment))
                    difficulty = escape_markdown(str(exercise.exercise.difficulty))
                    muscle_group = escape_markdown(str(exercise.exercise.muscle_group))

                    exercise_parts = [
                        f"\n• *{name}*",
                        f"  \\- Instructions: {instructions}",
                        f"  \\- Sets: {escape_markdown(str(exercise.sets))}",
                        f"  \\- Reps: {escape_markdown(str(exercise.reps))}",
                        f"  \\- Rest: {escape_markdown(str(exercise.rest_between_sets))}s",
                        f"  \\- Video: {escape_markdown(str(exercise.exercise.video_url))}",
                        f"  \\- Notes: {notes}",
                        f"  \\- Equipment: {equipment}",
                        f"  \\- Difficulty: {difficulty}",
                        f"  \\- Muscle Group: {muscle_group}",
                    ]

                    # Check if adding this exercise would exceed message limit
                    potential_message = "\n".join(
                        current_message + day_parts + exercise_parts
                    )
                    if (
                        len(potential_message) > 3800
                    ):  # Safe limit for markdown messages
                        messages.append("\n".join(current_message))
                        current_message = [week_header] + day_parts + exercise_parts
                    else:
                        if week_header:
                            current_message.append(week_header)
                            week_header = ""  # Clear week header after using it
                        current_message.extend(day_parts + exercise_parts)
                    day_parts = []  # Clear day parts after using them

        # Add any remaining content
        if current_message:
            if plan.notes:
                notes = escape_markdown(str(plan.notes))
                notes_section = ["\n\n📝 *Notes:*", notes]

                # Check if notes can fit in current message
                potential_message = "\n".join(current_message + notes_section)
                if len(potential_message) > 3800:
                    messages.append("\n".join(current_message))
                    messages.append("\n".join(notes_section))
                else:
                    current_message.extend(notes_section)
                    messages.append("\n".join(current_message))
            else:
                messages.append("\n".join(current_message))

        return messages


def main() -> None:
    """Start the bot."""
    try:
        # Create the Application
        logger.info("Initializing Telegram bot application")
        bot = GymBot()
        application = Application.builder().token(telegram_config.api_key).build()

        # Add handlers
        logger.info("Registering command handlers")
        application.add_handler(CommandHandler("start", bot.start_command))
        application.add_handler(CommandHandler("help", bot.help_command))
        application.add_handler(CommandHandler("end", bot.end_command))
        application.add_handler(CommandHandler("start_plan", bot.start_workout_plan))
        application.add_handler(CommandHandler("create_plan", bot.create_workout_plan))
        application.add_handler(
            CommandHandler("connect_calendar", bot.request_calendar_auth)
        )

        # Time preference handler (for initial time input)
        application.add_handler(
            MessageHandler(
                filters.Regex(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$") & ~filters.COMMAND,
                bot.handle_time_preference,
            )
        )

        # Time confirmation handler (for selecting suggested times)
        application.add_handler(
            MessageHandler(
                filters.Regex(r"^[1-9][0-9,\s]*$") & ~filters.COMMAND,
                bot.handle_time_confirmation,
            )
        )

        # Auth callback handler
        application.add_handler(
            MessageHandler(
                filters.Regex(r"^[0-9a-zA-Z\-_]+$") & ~filters.COMMAND,
                bot.handle_auth_callback,
            )
        )

        # Profile creation handler (should be last as it's the most general)
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_profile_creation)
        )

        # Add error handler
        application.add_error_handler(bot.error_handler)

        # Start the Bot
        logger.info("Starting bot polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception:
        logger.critical("Failed to start the bot", exc_info=True)
        raise
