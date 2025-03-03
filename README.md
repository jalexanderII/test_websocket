# Chat Application

A real-time chat application built with FastAPI, WebSocket, React, and OpenAI integration.

## Features

- Real-time chat with WebSocket support
- AI response, normal, stream, and structured stream
- React frontend with TypeScript and shadcn/ui components
- Chat history persistence
- Redis for managing AI response streams

## Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- Redis server
- OpenAI API key
- Bun (for frontend package management)
- uv (for Python package management)

## Setup

### Backend Setup

1. Clone the repository:

    ```bash
    git clone <repository-url>
    cd chat-app
    ```

2. Install uv if not already installed:

    ```bash
    pip install uv
    ```

3. Create and activate a virtual environment:

    ```bash
    uv venv
    source .venv/bin/activate
    ```

4. Install dependencies:

    ```bash
    uv sync
    ```

5. Create a `.env` file in the root directory with the following content:

    ```env
    DATABASE_URL=sqlite:///./chat.db
    OPENAI_API_KEY=your_openai_api_key_here
    MODEL_NAME=gpt-4o-mini
    HOST=0.0.0.0
    PORT=8005
    ENVIRONMENT=development
    
    # Redis Configuration
    REDIS_HOST=localhost
    REDIS_PORT=6379
    REDIS_DB=0
    REDIS_MAX_CONNECTIONS=20
    REDIS_RETRY_ATTEMPTS=5
    REDIS_CB_THRESHOLD=10
    REDIS_CB_TIMEOUT_MINS=5
    REDIS_SSL=false
    ```

6. Start Redis server (make sure Redis is installed):

    ```bash
    redis-server
    ```

7. Run the backend application:

    ```bash
    python -m app.main
    ```

The backend will be available at `http://localhost:8005`

### Frontend Setup

1. Navigate to the frontend directory:

    ```bash
    cd chat-frontend
    ```

2. Install dependencies:

    ```bash
    bun install
    ```

3. Start the development server:

    ```bash
    bun run dev
    ```

The frontend will be available at `http://localhost:5173`

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
    "chat_id": "123",
    "content": "Your message here"
}
```

Other available actions:

- `create_chat`: Create a new chat session
- `join_chat`: Join an existing chat session

### Response Format

Messages from the server will be in the following formats:

User/AI Message:

```json
{
    "type": "message",
    "message": {
        "id": "1",
        "chat_id": "123",
        "content": "Message content",
        "is_ai": false,
        "timestamp": "2024-01-27T00:00:00Z",
        "task_id": "abc-123"  // Only present for AI messages
    }
}
```

AI Stream Token:

```json
{
    "type": "token",
    "token": "Next token from AI",
    "task_id": "abc-123"
}
```

Generation Complete:

```json
{
    "type": "generation_complete",
    "task_id": "abc-123"
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
- `POST /api/chats/batch-delete` - Delete multiple chats
- `DELETE /api/users/{user_id}/chats/empty` - Delete empty chats for a user

## Architecture

The application follows a clean, layered architecture pattern designed for scalability and maintainability:

```ascii
┌──────────────────────────────────────────────────┐
│                Presentation Layer                │
│  ┌────────────────┐         ┌─────────────────┐  │
│  │  FastAPI       │         │     React UI    │  │
│  │  - WebSocket   │         │   (TypeScript)  │  │
│  │  - REST API    │         │                 │  │
│  └────────────────┘         └─────────────────┘  │
├──────────────────────────────────────────────────┤
│               Application Layer                  │
│  ┌────────────────┐    ┌───────────────────┐     │
│  │    Services    │    │ Task Processors   │     │
│  │  - Chat Logic  │    │ - Background Jobs │     │
│  │  - User Mgmt   │    │ - AI Processing   │     │
│  └────────────────┘    └───────────────────┘     │
├──────────────────────────────────────────────────┤
│                 Domain Layer                     │
│  ┌────────────────┐    ┌───────────────────┐     │
│  │Domain Models   │    │  Business Rules   │     │
│  │(Pydantic)      │    │                   │     │
│  └────────────────┘    └───────────────────┘     │
├──────────────────────────────────────────────────┤
│             Infrastructure Layer                 │
│  ┌──────────┐  ┌────────┐  ┌────────────────┐    │
│  │ Database │  │ Redis  │  │  OpenAI API    │    │
│  └──────────┘  └────────┘  └────────────────┘    │
└──────────────────────────────────────────────────┘
```

### Key Components

- FastAPI WebSocket/REST endpoints
- React frontend with shadcn/ui
- Background task processing
- WebSocket connection management
- Redis data structures