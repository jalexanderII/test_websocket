import asyncio
import json
import logging
import uuid
from typing import Dict

from fastapi import WebSocket
from pydantic import ValidationError

from app.api.handlers.websocket.connection_manager import ConnectionManager
from app.schemas.chat import Message, MessageCreate
from app.schemas.websocket import CreateChatMessage, JoinChatMessage, SendMessageRequest
from app.services.ai.adapter import ChatMessage
from app.services.ai.pipelines.manager import PipelineManager
from app.services.chat.service import ChatService
from app.services.core.background_task_processor import BackgroundTaskProcessor, TaskStatus
from app.utils.universal_serializer import safe_json_dumps

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


background_processor = BackgroundTaskProcessor(max_workers=5)


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

    async def handle_message(self, data: str) -> None:
        """Handle incoming WebSocket messages"""
        try:
            message_dict = json.loads(data)
            action = message_dict.get("action")
            logger.info("[WebSocket] Received action: %s with data: %s", action, message_dict)

            match action:
                case "create_chat":
                    message = CreateChatMessage(**message_dict)
                    logger.info("[WebSocket] Creating new chat for user: %s", self.user_id)
                    await self.handle_create_chat(message)
                case "send_message":
                    message = SendMessageRequest(**message_dict)
                    logger.info("[WebSocket] Sending message to chat: %s", message.chat_id)
                    await self.handle_send_message(message)
                case "join_chat":
                    message = JoinChatMessage(**message_dict)
                    logger.info("[WebSocket] Joining chat: %s", message.chat_id)
                    await self.handle_join_chat(message)
                case _:
                    logger.warning("[WebSocket] Unknown action received: %s", action)
                    await self._send_error(f"Unknown action: {action}")

        except ValidationError as e:
            logger.error("[WebSocket] Message validation error: %s", str(e))
            await self._send_error(str(e))
        except Exception as e:
            logger.exception("[WebSocket] Error handling message")
            await self._send_error(str(e))

    async def handle_send_message(self, message: SendMessageRequest):
        task_id = str(uuid.uuid4())
        logger.info("[WebSocket] Processing send message request. Chat: %s, Task: %s", message.chat_id, task_id)

        try:
            # First verify the chat exists and create user message
            chat = await self.chat_service.get_chat(message.chat_id)
            if not chat:
                logger.error("[WebSocket] Chat not found: %s", message.chat_id)
                raise ValueError("Chat not found")

            logger.info("[WebSocket] Creating user message in chat: %s", message.chat_id)
            # Create and save user message
            message_create = MessageCreate(
                chat_id=message.chat_id,
                content=message.content,
                is_ai=False,
            )
            user_message = await self.chat_service.send_message(message_create)
            await self._broadcast_user_message(user_message)

            # Get chat history for context
            history = await self.chat_service.get_chat_history(message.chat_id)
            logger.info("[WebSocket] Retrieved chat history, starting pipeline processing")

            # Start pipeline processing in background
            pipeline_type = message.pipeline_type if message.pipeline_type else "standard"
            logger.info("[WebSocket] Starting pipeline processing with type: %s", pipeline_type)

            # Create a wrapper function to ensure all arguments are passed correctly
            async def process_pipeline_wrapper():
                return await self._process_pipeline_message(
                    message=message.content,
                    pipeline_type=pipeline_type,
                    history=history,
                    chat_id=message.chat_id,
                    task_id=task_id,
                )

            process_task_id = await background_processor.add_task(process_pipeline_wrapper)

            logger.info("[WebSocket] Created pipeline task: %s", process_task_id)
            # Monitor the background task
            await self._monitor_task(process_task_id)

        except Exception as e:
            logger.exception("[WebSocket] Error handling message")
            await self._send_error(str(e))

    async def _process_pipeline_message(
        self,
        message: str,
        pipeline_type: str,
        history: list[ChatMessage],
        chat_id: int,
        task_id: str,
    ) -> dict:
        """Process a message through the pipeline in the background"""
        try:
            complete_response = ""
            async for response in self.pipeline_manager.process_message(
                message=message, pipeline_type=pipeline_type, history=history
            ):
                if response.response_type == "stream":
                    # Send streaming token but don't save yet
                    complete_response += response.content
                    await self.manager.broadcast_to_user(
                        self.user_id,
                        safe_json_dumps(
                            {
                                "type": "token",
                                "content": response.content,
                                "task_id": task_id,
                                "chat_id": chat_id,
                            }
                        ),
                    )
                elif response.response_type == "structured":
                    # Send structured response
                    complete_response = response.content
                    await self.manager.broadcast_to_user(
                        self.user_id,
                        safe_json_dumps(
                            {
                                "type": "structured_response",
                                "content": response.content,
                                "task_id": task_id,
                                "chat_id": chat_id,
                                "metadata": response.metadata,
                            }
                        ),
                    )

            # Save the complete AI message to DB without broadcasting
            message_create = MessageCreate(
                chat_id=chat_id,
                content=complete_response,
                is_ai=True,
                task_id=task_id,
            )
            await self.chat_service.send_message(message_create)

            # Send completion notification
            await self.manager.broadcast_to_user(
                self.user_id,
                safe_json_dumps(
                    {
                        "type": "generation_complete",
                        "task_id": task_id,
                    }
                ),
            )

            return {"content": complete_response}

        except Exception:
            logger.exception("Error processing message through pipeline")
            raise

    async def handle_create_chat(self, message: CreateChatMessage):
        try:
            # Create chat in background
            create_task_id = await background_processor.add_task(self.chat_service.create_chat, message.user_id)
            await self._monitor_task(create_task_id)

            # Get the created chat result
            task_data = await background_processor.get_task_result(create_task_id)
            if not task_data:
                raise Exception("Failed to get chat creation result")

            result = task_data.get("result")
            if not isinstance(result, dict):
                raise Exception("Invalid chat result")

            chat_id = result.get("id")
            if not chat_id:
                raise Exception("Chat result missing ID")

            logger.info("Chat created successfully with id: %s", chat_id)

            # Send chat_created event
            await self.manager.broadcast_to_user(
                self.user_id,
                safe_json_dumps(
                    {
                        "type": "chat_created",
                        "chat_id": chat_id,
                        "message": message.initial_message if message.initial_message else None,
                    }
                ),
            )

            # If there's an initial message, send it and get AI response
            if message.initial_message:
                # Send initial message
                message_task_id = await background_processor.add_task(
                    self._handle_initial_message, chat_id, message.initial_message or ""
                )
                await self._monitor_task(message_task_id)

                # Get chat history for context
                history = await self.chat_service.get_chat_history(chat_id)
                logger.info("[WebSocket] Retrieved chat history, starting pipeline processing")

                # Start pipeline processing in background
                pipeline_type = message.pipeline_type if message.pipeline_type else "standard"
                logger.info("[WebSocket] Starting pipeline processing with type: %s", pipeline_type)

                pipeline_task_id = str(uuid.uuid4())

                # Start pipeline processing in background with standard type
                async def process_pipeline_wrapper():
                    return await self._process_pipeline_message(
                        message=message.initial_message or "",
                        pipeline_type=pipeline_type,
                        history=history,
                        chat_id=chat_id,
                        task_id=pipeline_task_id,
                    )

                ai_task_id = await background_processor.add_task(process_pipeline_wrapper)
                await self._monitor_task(ai_task_id)

        except Exception as e:
            logger.exception("Error creating chat")
            await self._send_error(str(e))

    async def _handle_initial_message(self, chat_id: int, content: str) -> None:
        """Handle sending the initial message in a new chat"""
        message_create = MessageCreate(
            chat_id=chat_id,
            content=content,
            is_ai=False,
        )
        message = await self.chat_service.send_message(message_create)
        await self._broadcast_user_message(message)

    async def handle_join_chat(self, message: JoinChatMessage):
        try:
            logger.info("[WebSocket] Starting join chat process for chat: %s", message.chat_id)
            # Verify chat exists in background
            task_id = await background_processor.add_task(self.chat_service.get_chat, message.chat_id)
            logger.info("[WebSocket] Created background task %s for joining chat", task_id)

            # Monitor task completion with timeout
            max_retries = 10
            retry_count = 0
            while retry_count < max_retries:
                task_data = await background_processor.get_task_result(task_id)
                logger.debug("[WebSocket] Join chat task data: %s", task_data)

                if not task_data:
                    await asyncio.sleep(0.1)
                    retry_count += 1
                    continue

                status = task_data.get("status")
                logger.info("[WebSocket] Join chat task status: %s", status)

                if status == TaskStatus.COMPLETED:
                    result = task_data.get("result")
                    if not result:
                        logger.error("[WebSocket] Chat not found: %s", message.chat_id)
                        raise ValueError("Chat not found")

                    logger.info("[WebSocket] Successfully joined chat: %s", message.chat_id)
                    await self.manager.broadcast_to_user(
                        self.user_id,
                        safe_json_dumps(
                            {
                                "type": "chat_joined",
                                "chat_id": message.chat_id,
                            }
                        ),
                    )
                    return
                elif status in [TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    error = task_data.get("error", "Unknown error")
                    logger.error("[WebSocket] Failed to join chat: %s", error)
                    raise Exception(f"Failed to join chat: {error}")

                await asyncio.sleep(0.1)
                retry_count += 1

            logger.error("[WebSocket] Timeout waiting to join chat: %s", message.chat_id)
            raise Exception("Timeout waiting to join chat")

        except Exception as e:
            logger.exception("[WebSocket] Error joining chat")
            await self._send_error(str(e))

    async def _broadcast_user_message(self, message: Message) -> None:
        """Broadcast a user message to all connected clients"""
        try:
            # Ensure message is JSON serializable
            message_data = message.model_dump(mode="json") if hasattr(message, "model_dump") else message
            await self.manager.broadcast_to_user(
                self.user_id,
                safe_json_dumps({"type": "message", "message": message_data}),
            )
        except Exception:
            logger.exception("Error broadcasting user message")
            raise

    async def _send_error(self, error: str) -> None:
        """Send an error message to the client"""
        try:
            await self.manager.broadcast_to_user(
                self.user_id,
                safe_json_dumps({"type": "error", "message": error}),
            )
        except Exception:
            logger.exception("Error sending error message")
            # If we can't send the error, just log it
            pass

    async def _monitor_task(self, task_id: str) -> None:
        """Monitor a background task and send updates"""
        try:
            while True:
                # Wait for task to be ready
                await asyncio.sleep(0.1)

                task_data = await background_processor.get_task_result(task_id)
                if not task_data:
                    logger.error("Task %s not found", task_id)
                    await self._send_error(f"Task {task_id} not found")
                    break

                status = task_data.get("status")
                if not status:
                    logger.error("Task %s has no status", task_id)
                    break

                if status == TaskStatus.COMPLETED:
                    # Task completed successfully
                    # Ensure result is JSON serializable
                    result = safe_json_dumps(task_data.get("result", {}))
                    await self.manager.broadcast_to_user(
                        self.user_id,
                        safe_json_dumps(
                            {
                                "type": "task_completed",
                                "task_id": task_id,
                                "result": result,
                            }
                        ),
                    )
                    break
                elif status == TaskStatus.FAILED:
                    # Task failed
                    error = task_data.get("error", "Unknown error")
                    await self.manager.broadcast_to_user(
                        self.user_id,
                        safe_json_dumps(
                            {
                                "type": "task_failed",
                                "task_id": task_id,
                                "error": str(error),
                            }
                        ),
                    )
                    break
                elif status == TaskStatus.CANCELLED:
                    # Task was cancelled
                    await self.manager.broadcast_to_user(
                        self.user_id,
                        safe_json_dumps(
                            {
                                "type": "task_cancelled",
                                "task_id": task_id,
                            }
                        ),
                    )
                    break

                # Continue monitoring if task is still running
                await asyncio.sleep(0.1)

        except Exception as e:
            logger.exception("Error monitoring task %s", task_id)
            await self._send_error(str(e))

    async def _generate_structured_response(self, chat_id: int, user_message: str) -> Dict:
        """Generate a structured AI response"""
        try:
            latest_response = None
            task_id = str(uuid.uuid4())  # Generate a task ID for this response
            async for response in self.chat_service.stream_structured_ai_response(
                chat_id=chat_id, user_message=user_message, task_id=task_id
            ):
                latest_response = response
                # Send progress update
                await self.manager.broadcast_to_user(
                    self.user_id,
                    safe_json_dumps(
                        {
                            "type": "structured_response",
                            "content": response.model_dump() if hasattr(response, "model_dump") else response,
                            "task_id": task_id,
                            "chat_id": chat_id,
                            "metadata": response.model_dump().get("metadata")
                            if hasattr(response, "model_dump")
                            else None,
                        }
                    ),
                )
            return {
                "content": (
                    latest_response
                    if isinstance(latest_response, dict)
                    else latest_response.model_dump()
                    if latest_response
                    else {}
                ),
                "task_id": task_id,
            }
        except Exception:
            logger.exception("Error generating structured response")
            raise

    async def _generate_standard_response(self, chat_id: int, user_message: str) -> Dict:
        """Generate a standard AI response"""
        try:
            complete_response = ""
            task_id = str(uuid.uuid4())  # Generate a task ID for this response
            async for token in self.chat_service.stream_ai_response(
                chat_id=chat_id, user_message=user_message, task_id=task_id
            ):
                complete_response += token
                # Send progress update
                await self.manager.broadcast_to_user(
                    self.user_id,
                    safe_json_dumps(
                        {
                            "type": "token",
                            "content": token,
                            "chat_id": chat_id,
                            "task_id": task_id,
                        }
                    ),
                )
            return {"content": complete_response, "task_id": task_id}
        except Exception:
            logger.exception("Error generating standard response")
            raise
