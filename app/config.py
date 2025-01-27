import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chat.db")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8005"))
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Validate required environment variables
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")


class TestConfig:
    DATABASE_URL = "sqlite:///./test.db"  # Use SQLite for testing
