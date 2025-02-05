# src/calendar/auth.py
import logging
import os
import pickle

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from src.models._types import UserId


logger = logging.getLogger(__name__)


class CalendarAuth:
    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    TOKEN_DIR = "tokens"
    CLIENT_SECRETS_FILE = "client_secrets.json"

    def __init__(self) -> None:
        self.token_dir = self.TOKEN_DIR
        try:
            os.makedirs(self.token_dir, exist_ok=True)
        except PermissionError as e:
            logger.error(f"Failed to create token directory: {e}")
            raise

    def __get_token_path(self, user_id: UserId) -> str:
        return os.path.join(self.token_dir, f"token_{user_id}.pickle")

    def get_credentials(self, user_id: UserId) -> Credentials | None:
        """Get stored credentials or None if not found"""
        try:
            token_path = self.__get_token_path(user_id)
            if not os.path.exists(token_path):
                logger.info(f"No token file found for user {user_id} at {token_path}")
                return None

            logger.debug(f"Loading credentials from {token_path}")
            with open(token_path, "rb") as token:
                creds = pickle.load(token)

            if not isinstance(creds, Credentials):
                logger.error(f"Invalid credential format for user {user_id}")
                return None

            if creds.valid:
                logger.debug(f"Valid credentials found for user {user_id}")
                return creds
            if creds.expired and creds.refresh_token:
                logger.info(f"Refreshing expired token for user {user_id}")
                try:
                    creds.refresh(Request())
                    self.__save_credentials(user_id, creds)
                    logger.info(f"Successfully refreshed token for user {user_id}")
                    return creds
                except Exception as e:
                    logger.error(f"Failed to refresh token for user {user_id}: {e}")
                    return None
            logger.info(
                f"Invalid credentials state for user {user_id}: "
                f"expired={creds.expired}, "
                f"has_refresh_token={bool(creds.refresh_token)}"
            )
            return None
        except Exception as e:
            logger.error(f"Error getting credentials for user {user_id}: {e}")
            return None

    def start_auth_flow(self, user_id: UserId) -> InstalledAppFlow:
        """Start OAuth flow"""
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.CLIENT_SECRETS_FILE, self.SCOPES
            )
            # Use Google's OAuth device flow instead
            flow.run_local_server(
                port=0
            )  # This will automatically handle the OAuth flow
            creds = flow.credentials
            self.__save_credentials(user_id, creds)
            logger.info(f"Successfully saved credentials for user {user_id}")
            return flow
        except Exception as e:
            logger.error(f"Failed to start auth flow: {e}")
            raise

    def __save_credentials(self, user_id: int, creds: Credentials) -> None:
        """Save credentials to file"""
        token_path = self.__get_token_path(user_id)
        temp_path = f"{token_path}.tmp"
        try:
            logger.debug(f"Saving credentials for user {user_id} to {token_path}")
            os.makedirs(os.path.dirname(token_path), exist_ok=True)

            with open(temp_path, "wb") as token:
                pickle.dump(creds, token)
            os.replace(temp_path, token_path)
            logger.info(f"Successfully saved credentials for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to save credentials for user {user_id}: {e}")
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def delete_credentials(self, user_id: UserId) -> None:
        token_path = self.__get_token_path(user_id)
        if os.path.exists(token_path):
            os.unlink(token_path)
            logger.info(f"Deleted calendar credentials for user {user_id}")
