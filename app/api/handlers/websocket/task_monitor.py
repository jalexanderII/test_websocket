import asyncio
from typing import Any, Awaitable

from api.handlers.websocket.websocket_handler import WebSocketHandler

from app.config.logger import get_logger
from app.config.settings import settings
from app.services.core.background_task_processor import BackgroundTaskProcessor, TaskStatus

logger = get_logger(__name__)


background_processor = BackgroundTaskProcessor(max_workers=settings.BACKGROUND_TASK_PROCESSOR_MAX_WORKERS)


class TaskMonitor:
    """Simplified task monitoring"""

    def __init__(self, handler: WebSocketHandler):
        self.handler = handler

    async def run_and_monitor(self, task_id: str, coro: Awaitable[Any], timeout: float = 30.0) -> Any:
        """Run a coroutine with timeout and status updates"""
        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            await self.handler.broadcast("task_completed", task_id=task_id, result=result)
            return result
        except TimeoutError:
            await self.handler.broadcast("task_timeout", task_id=task_id)
            raise
        except Exception as e:
            await self.handler.broadcast("task_failed", task_id=task_id, error=str(e))
            raise

    async def monitor_background_task(self, task_id: str, timeout: float = 30.0) -> Any:
        """Monitor a background task and handle its completion"""
        start_time = asyncio.get_event_loop().time()

        while True:
            if asyncio.get_event_loop().time() - start_time >= timeout:
                await self.handler.broadcast("task_timeout", task_id=task_id)
                raise TimeoutError(f"Task {task_id} timed out")

            task_data = await background_processor.get_task_result(task_id)
            if not task_data:
                await asyncio.sleep(0.1)
                continue

            status = task_data.get("status")
            if status == TaskStatus.COMPLETED:
                result = task_data.get("result")
                await self.handler.broadcast("task_completed", task_id=task_id, result=result)
                return result
            elif status in [TaskStatus.FAILED, TaskStatus.CANCELLED]:
                error = task_data.get("error", "Unknown error")
                await self.handler.broadcast("task_failed", task_id=task_id, error=error)
                raise Exception(error)

            await asyncio.sleep(0.1)
