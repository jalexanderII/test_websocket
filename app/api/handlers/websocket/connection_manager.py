import logging
from datetime import datetime, timezone
from typing import Dict, Set as PySet

from fastapi import WebSocket
from pydantic import BaseModel
from redis_data_structures import Dict as RedisDict, Set

from app.config.redis import redis_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebSocketConnection(BaseModel):
    """Model for storing websocket connection metadata"""

    user_id: int
    last_heartbeat: datetime
    client_info: dict
    connection_count: int


class ConnectionManager:
    def __init__(self):
        self.active_users: Set = Set("active_users", connection_manager=redis_manager)
        self.connection_metadata = RedisDict("connection_metadata", connection_manager=redis_manager)
        self._connections: Dict[int, PySet[WebSocket]] = {}
        self._last_heartbeat: Dict[WebSocket, float] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()

        self.active_users.add(user_id)

        # Update connection metadata
        meta_key = f"user:{user_id}"
        existing_meta = self.connection_metadata.get(meta_key)

        # Get client info safely
        try:
            client_ip = websocket.client.host if websocket.client else "unknown"
        except Exception:
            client_ip = "unknown"

        client_info = {"ip": client_ip}

        if existing_meta:
            connection_meta = WebSocketConnection.model_validate(existing_meta)
            connection_meta.connection_count += 1
            connection_meta.last_heartbeat = datetime.now(timezone.utc)
            connection_meta.client_info.update(client_info)
        else:
            connection_meta = WebSocketConnection(
                user_id=user_id, last_heartbeat=datetime.now(timezone.utc), client_info=client_info, connection_count=1
            )

        self.connection_metadata[meta_key] = connection_meta.model_dump(mode="json")

        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(websocket)
        self._last_heartbeat[websocket] = datetime.now(timezone.utc).timestamp()

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if websocket in self._last_heartbeat:
                del self._last_heartbeat[websocket]

            # Update connection metadata
            meta_key = f"user:{user_id}"
            if meta := self.connection_metadata.get(meta_key):
                connection_meta = WebSocketConnection.model_validate(meta)
                connection_meta.connection_count -= 1

                if connection_meta.connection_count <= 0:
                    del self.connection_metadata[meta_key]
                    self.active_users.remove(user_id)
                else:
                    self.connection_metadata[meta_key] = connection_meta.model_dump()

            if not self._connections[user_id]:
                del self._connections[user_id]

    async def broadcast_to_user(self, user_id: int, message: str):
        if user_id in self._connections:
            connections = list(self._connections[user_id])
            for connection in connections:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.exception("Failed to send message to user %s: %s", user_id, str(e))
                    await self.handle_failed_connection(connection, user_id)

    async def handle_failed_connection(self, websocket: WebSocket, user_id: int):
        """Handle cleanup of failed connections"""
        self.disconnect(websocket, user_id)

    def update_heartbeat(self, websocket: WebSocket):
        """Update last heartbeat time for a connection"""
        self._last_heartbeat[websocket] = datetime.now(timezone.utc).timestamp()

    def is_connection_alive(self, websocket: WebSocket, timeout_seconds: int = 30) -> bool:
        """Check if a connection is still alive based on its last heartbeat"""
        if websocket not in self._last_heartbeat:
            return False
        last_heartbeat = self._last_heartbeat[websocket]
        current_time = datetime.now(timezone.utc).timestamp()
        return (current_time - last_heartbeat) < timeout_seconds

    def get_health_info(self) -> dict:
        """Get detailed health information about WebSocket connections"""
        current_time = datetime.now(timezone.utc).timestamp()
        active_connections = sum(len(list(connections)) for connections in self._connections.values())
        dead_connections = sum(1 for ws in self._last_heartbeat if (current_time - self._last_heartbeat[ws]) >= 30)

        return {
            "status": "healthy" if active_connections > 0 and dead_connections == 0 else "degraded",
            "active_users_count": self.active_users.size(),
            "total_connections": active_connections,
            "dead_connections": dead_connections,
            "connections_by_user": {
                user_id: len(list(connections)) for user_id, connections in self._connections.items()
            },
            "redis_health": redis_manager.health_check(),
            "last_heartbeat_stats": {
                "oldest_heartbeat": min(self._last_heartbeat.values()) if self._last_heartbeat else None,
                "newest_heartbeat": max(self._last_heartbeat.values()) if self._last_heartbeat else None,
                "total_tracked_heartbeats": len(self._last_heartbeat),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
