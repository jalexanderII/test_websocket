import asyncio
import json
import uuid
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

from fastapi import WebSocket

from app.api.handlers.websocket.connection_manager import ConnectionManager
from app.config.logger import get_logger
from app.config.settings import settings
from app.schemas.chat import Message, MessageCreate
from app.schemas.websocket import CreateChatMessage, JoinChatMessage, SendMessageRequest
from app.services.ai.adapter import ChatMessage
from app.services.ai.pipelines.manager import PipelineManager
from app.services.chat.service import ChatService
from app.services.core.background_task_processor import BackgroundTaskProcessor, TaskData, TaskStatus
from app.utils.universal_serializer import safe_json_dumps

logger = get_logger(__name__)


background_processor = BackgroundTaskProcessor(max_workers=settings.BACKGROUND_TASK_PROCESSOR_MAX_WORKERS)

T = TypeVar("T")


def with_error_handling(f: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Simple decorator to handle errors consistently"""

    @wraps(f)
    async def wrapper(self, *args, **kwargs):
        try:
            return await f(self, *args, **kwargs)
        except Exception as e:
            await self._send_error(str(e))
            raise

    return wrapper


class TaskMonitor:
    """Simplified task monitoring"""

    def __init__(self, handler: "WebSocketHandler"):
        self.handler = handler

    async def _handle_task_update(self, task_data: TaskData) -> Any:
        """Handle a task update from Redis and return the result"""
        try:
            status = task_data.get("status")
            task_id = task_data.get("task_id", "")  # Ensure we have a string for task_id
            logger.debug("[TaskMonitor] Processing task update - status: %s, data: %s", status, task_data)

            if status == TaskStatus.COMPLETED:
                result = task_data.get("data", {}).get("result")
                logger.debug("[TaskMonitor] Task completed with result: %s", result)
                await self.handler.broadcast(
                    "task_completed",
                    task_id=task_id,
                    result=result,
                )
                return result
            elif status == TaskStatus.FAILED:
                error = task_data.get("error", "Unknown error")
                logger.debug("[TaskMonitor] Task failed with error: %s", error)
                await self.handler.broadcast(
                    "task_failed",
                    task_id=task_id,
                    error=error,
                )
                raise Exception(error)
            elif status == TaskStatus.CANCELLED:
                logger.debug("[TaskMonitor] Task was cancelled")
                await self.handler.broadcast(
                    "task_cancelled",
                    task_id=task_id,
                )
                raise Exception("Task cancelled")
            return None
        except Exception as e:
            logger.exception("Error handling task update")
            await self.handler._send_error(str(e))
            raise

    async def monitor_background_task(self, task_id: str, timeout_seconds: float = 30.0) -> Any:
        """Monitor a background task using Redis pub/sub and return the result on completion"""
        try:
            # Get Redis pubsub connection from background processor
            pubsub = await background_processor.subscribe_to_task_updates(task_id)

            try:
                # Set timeout
                start_time = asyncio.get_event_loop().time()

                # Check initial status in case task completed before we subscribed
                task_data = await background_processor.get_task_result(task_id)
                logger.debug("[TaskMonitor] Initial task data for %s: %s", task_id, task_data)

                if task_data:
                    logger.debug(
                        "[TaskMonitor] Task status: %s, result: %s", task_data.get("status"), task_data.get("result")
                    )

                if task_data and task_data["status"] in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    return await self._handle_task_update(task_data)

                # Wait for updates
                while True:
                    # Check timeout
                    if asyncio.get_event_loop().time() - start_time >= timeout_seconds:
                        logger.warning("Task %s monitoring timed out after %.1f seconds", task_id, timeout_seconds)
                        await self.handler.broadcast(
                            "task_timeout",
                            task_id=task_id,
                            message=f"Task monitoring timed out after {timeout_seconds} seconds",
                        )
                        raise TimeoutError(f"Task {task_id} timed out")

                    # Wait for message with timeout
                    message = await pubsub.get_message(timeout=1.0)
                    if message and message["type"] == "message":
                        try:
                            logger.debug("[TaskMonitor] Received message for %s: %s", task_id, message)
                            data = json.loads(message["data"])
                            result = await self._handle_task_update(data)
                            # If the status indicates completion, return the result
                            if data.get("status", "") in [
                                TaskStatus.COMPLETED,
                                TaskStatus.FAILED,
                                TaskStatus.CANCELLED,
                            ]:
                                return result
                        except json.JSONDecodeError:
                            logger.warning("Failed to decode message data: %s", message["data"])
                            continue

            finally:
                # Always unsubscribe and close connection
                await pubsub.unsubscribe()
                await pubsub.close()

        except Exception as e:
            logger.exception("Error monitoring task %s", task_id)
            await self.handler._send_error(str(e))
            raise


class WebSocketHandler:
    def __init__(
        self,
        websocket: WebSocket,
        user_id: int,
        chat_service: ChatService,
        connection_manager: ConnectionManager,
    ):
        self.websocket = websocket
        self.user_id = user_id
        self.chat_service = chat_service
        self.manager = connection_manager
        self.pipeline_manager = PipelineManager()
        self.task_monitor = TaskMonitor(self)

        # Simple action -> handler mapping
        self.handlers = {
            "create_chat": self._handle_create_chat_message,
            "send_message": self._handle_send_message_action,
            "join_chat": self._handle_join_chat_message,
        }

    async def broadcast(self, message_type: str, **data) -> None:
        """Centralized broadcasting with consistent format"""
        try:
            await self.manager.broadcast_to_user(self.user_id, safe_json_dumps({"type": message_type, **data}))
        except Exception:
            logger.exception("Error broadcasting message")
            raise

    @with_error_handling
    async def handle_message(self, data: str) -> None:
        """Handle incoming WebSocket messages"""
        message_dict = json.loads(data)
        action = message_dict.get("action")
        logger.info("[WebSocket] Received action: %s with data: %s", action, message_dict)

        handler = self.handlers.get(action)
        if not handler:
            logger.warning("[WebSocket] Unknown action received: %s", action)
            await self._send_error(f"Unknown action: {action}")
            return

        # Parse message based on action type
        try:
            if action == "create_chat":
                message = CreateChatMessage(**message_dict)
            elif action == "send_message":
                message = SendMessageRequest(**message_dict)
            elif action == "join_chat":
                message = JoinChatMessage(**message_dict)

            await handler(message)
        except Exception as e:
            logger.error("[WebSocket] Message validation error: %s", str(e))
            raise

    async def _handle_create_chat_message(self, message: CreateChatMessage):
        """Handle create chat message after validation"""

        # First, generate a task ID we'll use for both monitoring and task creation
        create_task_id = str(uuid.uuid4())
        logger.debug("[WebSocket] Generated task ID for chat creation: %s", create_task_id)

        # Set up monitoring BEFORE creating the task
        pubsub = await background_processor.subscribe_to_task_updates(create_task_id)
        try:
            # Create chat in background with proper serialization
            async def create_chat_wrapper(user_id: int):
                chat = await self.chat_service.create_chat(user_id)
                if not chat:
                    logger.error("[WebSocket] Chat creation failed - no chat returned")
                    raise Exception("Chat creation failed")
                result = chat.model_dump()
                logger.debug("[WebSocket] Chat created and serialized: %s", result)
                return result

            # Now start the task with our pre-generated ID
            await background_processor.add_task(create_chat_wrapper, message.user_id, task_id=create_task_id)
            logger.debug("[WebSocket] Created background task for chat creation: %s", create_task_id)

            # Monitor the task now that we're already subscribed
            result = await self.task_monitor.monitor_background_task(create_task_id)
            logger.debug("[WebSocket] Final task result: %s", result)

            # Result should be a serialized Chat model
            if not isinstance(result, dict):
                logger.error("[WebSocket] Invalid chat creation result type: %s", type(result))
                raise Exception("Invalid chat creation result")

            if "id" not in result:
                logger.error("[WebSocket] Chat result missing id field: %s", result)
                raise Exception("Invalid chat creation result: missing id field")

            chat_id = result["id"]
            logger.info("Chat created successfully with id: %s", chat_id)

            # Send chat_created event
            await self.broadcast(
                "chat_created",
                chat_id=chat_id,
            )

            # Handle initial message if provided
            if message.initial_message:
                await self._process_initial_chat_message(chat_id, message.initial_message)

        finally:
            # Clean up subscription
            await pubsub.unsubscribe()
            await pubsub.close()

    async def _process_initial_chat_message(self, chat_id: int, initial_message: str):
        """Process the initial message for a newly created chat"""
        # Send initial message
        message_task_id = await background_processor.add_task(self._handle_initial_message, chat_id, initial_message)
        await self.task_monitor.monitor_background_task(message_task_id)

        # Update chat title
        title_process_id = await background_processor.add_task(self.update_title_wrapper, chat_id, initial_message)
        logger.info("[WebSocket] Created title update task: %s", title_process_id)
        await self.task_monitor.monitor_background_task(title_process_id)

        # Process AI response
        history = await self.chat_service.get_chat_history(chat_id)
        logger.info("[WebSocket] Retrieved chat history, starting pipeline processing")

        async def process_pipeline_wrapper():
            return await self._process_pipeline_message(
                message=initial_message,
                history=history,
                chat_id=chat_id,
                task_id=str(uuid.uuid4()),
            )

        ai_task_id = await background_processor.add_task(process_pipeline_wrapper)
        await self.task_monitor.monitor_background_task(ai_task_id)

    async def _handle_send_message_action(self, message: SendMessageRequest):
        """Handle send message action after validation"""
        task_id = str(uuid.uuid4())
        logger.info("[WebSocket] Processing send message request. Chat: %s, Task: %s", message.chat_id, task_id)

        # Verify chat exists
        chat = await self.chat_service.get_chat(message.chat_id)
        if not chat:
            logger.error("[WebSocket] Chat not found: %s", message.chat_id)
            raise ValueError("Chat not found")

        # Create and save user message
        user_message = await self.chat_service.send_message(
            MessageCreate(
                chat_id=message.chat_id,
                content=message.content,
                is_ai=False,
            )
        )
        await self._broadcast_user_message(user_message)

        # Process message in background
        await self._process_message_with_ai(message.chat_id, message.content, task_id)

    async def _process_message_with_ai(self, chat_id: int, content: str, task_id: str):
        """Process a message with AI in the background"""
        # Update title
        title_process_id = await background_processor.add_task(self.update_title_wrapper, chat_id, content)
        logger.info("[WebSocket] Created title update task: %s", title_process_id)

        # Get chat history and process message
        history = await self.chat_service.get_chat_history(chat_id)
        logger.info("[WebSocket] Retrieved chat history, starting pipeline processing")

        async def process_pipeline_wrapper():
            return await self._process_pipeline_message(
                message=content,
                history=history,
                chat_id=chat_id,
                task_id=task_id,
            )

        process_task_id = await background_processor.add_task(process_pipeline_wrapper)
        logger.info("[WebSocket] Created pipeline task: %s", process_task_id)

        # Monitor both tasks
        await asyncio.gather(
            self.task_monitor.monitor_background_task(title_process_id),
            self.task_monitor.monitor_background_task(process_task_id),
        )

    async def _handle_join_chat_message(self, message: JoinChatMessage):
        """Handle join chat message after validation"""
        logger.info("[WebSocket] Starting join chat process for chat: %s", message.chat_id)

        task_id = await background_processor.add_task(self.chat_service.get_chat, message.chat_id)
        logger.info("[WebSocket] Created background task %s for joining chat", task_id)

        await self.task_monitor.monitor_background_task(task_id, timeout_seconds=10.0)
        # The task monitor will raise an exception if the task fails or times out
        # If we get here, the task completed successfully and result contains the chat

        logger.info("[WebSocket] Successfully joined chat: %s", message.chat_id)
        await self.broadcast("chat_joined", chat_id=message.chat_id)

    async def _process_pipeline_message(
        self,
        message: str,
        history: list[ChatMessage],
        chat_id: int,
        task_id: str,
    ) -> dict:
        """Process a message through the pipeline in the background"""
        try:
            complete_response = ""
            async for response in self.pipeline_manager.process_message(message=message, history=history):
                if response.response_type == "stream":
                    complete_response += response.content
                    await self.broadcast(
                        "token",
                        content=response.content,
                        task_id=task_id,
                        chat_id=chat_id,
                    )
                elif response.response_type == "structured":
                    complete_response = response.content
                    await self.broadcast(
                        "structured_response",
                        content=response.content,
                        task_id=task_id,
                        chat_id=chat_id,
                        metadata=response.metadata,
                    )

            # Save the complete AI message
            await self.chat_service.send_message(
                MessageCreate(
                    chat_id=chat_id,
                    content=complete_response,
                    is_ai=True,
                    task_id=task_id,
                )
            )

            await self.broadcast("generation_complete", task_id=task_id)
            return {"content": complete_response}

        except Exception:
            logger.exception("Error processing message through pipeline")
            raise

    async def update_title_wrapper(self, chat_id: int, initial_message: str):
        logger.info("[WebSocket] Attempting to update chat title for chat %s", chat_id)
        title = await self.chat_service.update_chat_title(chat_id, initial_message)
        logger.info("[WebSocket] Title update result: %s", title)
        if title:  # Only broadcast if we got a new title
            logger.info("[WebSocket] Broadcasting title update: chat_id=%s, title=%s", chat_id, title)
            await self.broadcast("update_title", chat_id=chat_id, title=title)
        return {"title": title}

    async def _handle_initial_message(self, chat_id: int, content: str) -> None:
        """Handle sending the initial message in a new chat"""
        message_create = MessageCreate(
            chat_id=chat_id,
            content=content,
            is_ai=False,
        )
        message = await self.chat_service.send_message(message_create)
        await self._broadcast_user_message(message)

    async def _broadcast_user_message(self, message: Message) -> None:
        """Broadcast a user message to all connected clients"""
        message_data = message.model_dump(mode="json") if hasattr(message, "model_dump") else message
        await self.broadcast("message", message=message_data)

    async def _send_error(self, error: str) -> None:
        """Send an error message to the client"""
        await self.broadcast("error", message=error)
