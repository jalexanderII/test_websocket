from typing import Any


class WebSocketError(Exception):
    """Base exception for WebSocket errors"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class MessageValidationError(WebSocketError):
    """Raised when message validation fails"""

    pass


class ChatNotFoundError(WebSocketError):
    """Raised when a chat is not found"""

    pass


class TaskTimeoutError(WebSocketError):
    """Raised when a task times out"""

    pass


class PipelineProcessingError(WebSocketError):
    """Raised when pipeline processing fails"""

    pass


class UnauthorizedError(WebSocketError):
    """Raised when user is not authorized for an operation"""

    pass


class ConnectionError(WebSocketError):
    """Raised when there are connection issues"""

    pass
