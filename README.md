# Chat Application

A real-time chat application built with FastAPI, WebSocket, and OpenAI integration.

## Features

- Real-time chat with WebSocket support
- AI-powered responses using OpenAI's GPT models
- Ability to abort running AI responses
- Chat history persistence
- Scalable architecture following clean architecture principles

## Prerequisites

- Python 3.11 or higher
- OpenAI API key

## Setup

1. Clone the repository:

```bash
git clone <repository-url>
cd chat-app
```

2. Create and activate a virtual environment:

```bash
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:

```bash
uv sync
```

4. Create a `.env` file in the root directory with the following content:

```
DATABASE_URL=sqlite:///./chat.db
OPENAI_API_KEY=your_openai_api_key_here
MODEL_NAME=gpt-3.5-turbo
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=development
```

5. Run the application:

```bash
python -m app.main
```

The application will be available at `http://localhost:8005`

## API Documentation

Once the application is running, you can access the API documentation at:

- Swagger UI: `http://localhost:8005/docs`
- ReDoc: `http://localhost:8005/redoc`

## WebSocket Usage

Connect to the WebSocket endpoint at `ws://localhost:8005/ws/{user_id}`

### Message Format

Send messages in the following JSON format:

```json
{
    "action": "send_message",
    "chat_id": 123,
    "content": "Your message here"
}
```

To abort a running AI response:

```json
{
    "action": "abort",
    "task_id": "task-uuid-here"
}
```

### Response Format

Messages from the server will be in the following formats:

User/AI Message:

```json
{
    "type": "message",
    "message": {
        "id": 1,
        "content": "Message content",
        "is_ai": false,
        "timestamp": "2024-01-27T00:00:00Z"
    }
}
```

AI Stream Token:

```json
{
    "type": "token",
    "token": "Next token from AI"
}
```

Abort Confirmation:

```json
{
    "type": "aborted",
    "task_id": "task-uuid-here"
}
```

Error:

```json
{
    "type": "error",
    "message": "Error description"
}
```

## HTTP Endpoints

- `POST /api/chats` - Create a new chat
- `GET /api/chats/{chat_id}` - Get chat details
- `GET /api/users/{user_id}/chats` - Get user's chats
- `POST /api/chats/{chat_id}/abort` - Abort an AI response

## Architecture

The application follows a clean architecture pattern with the following layers:

- Presentation Layer (FastAPI endpoints)
- Application Layer (Services and Task Management)
- Domain Layer (Core Business Logic)
- Infrastructure Layer (Database, External Services)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License.
