from datetime import UTC, datetime
from typing import Dict, List, Set as PySet

from fastapi import WebSocket
from pydantic import BaseModel

from app.config.logger import get_logger
from app.config.redis import async_redis
from app.utils.async_redis_utils.connection import AsyncConnectionManager
from app.utils.async_redis_utils.dict import AsyncDict
from app.utils.async_redis_utils.set import AsyncSet

logger = get_logger(__name__)


class WebSocketConnection(BaseModel):
    """Model for storing websocket connection metadata"""

    user_id: int
    last_heartbeat: datetime
    client_info: dict
    connection_count: int


class ConnectionManager:
    def __init__(self, async_redis: AsyncConnectionManager):
        """Initialize the connection manager with Redis-backed data structures."""
        self.active_users: AsyncSet = AsyncSet("active_users", connection_manager=async_redis)
        self.connection_metadata = AsyncDict("connection_metadata", connection_manager=async_redis)
        self._connections: Dict[int, PySet[WebSocket]] = {}
        self._last_heartbeat: Dict[WebSocket, float] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        logger.debug("Accepting websocket connection")
        await websocket.accept()
        logger.debug("Websocket connection accepted")

        logger.debug("Adding user to active users")
        await self.active_users.add(user_id)
        logger.debug("User added to active users")

        # Update connection metadata
        meta_key = f"user:{user_id}"
        logger.debug("Getting existing metadata for key: %s", meta_key)
        existing_meta = await self.connection_metadata.get(meta_key)
        logger.debug("Got existing metadata: %s", existing_meta)

        # Get client info safely
        try:
            client_ip = websocket.client.host if websocket.client else "unknown"
        except Exception:
            client_ip = "unknown"
        logger.debug("Got client IP: %s", client_ip)

        client_info = {"ip": client_ip}

        if existing_meta:
            logger.debug("Updating existing metadata")
            connection_meta = WebSocketConnection.model_validate(existing_meta)
            connection_meta.connection_count += 1
            connection_meta.last_heartbeat = datetime.now(UTC)
            connection_meta.client_info.update(client_info)
        else:
            logger.debug("Creating new metadata")
            connection_meta = WebSocketConnection(
                user_id=user_id, last_heartbeat=datetime.now(UTC), client_info=client_info, connection_count=1
            )

        logger.debug("Setting connection metadata")
        await self.connection_metadata.set(meta_key, connection_meta.model_dump(mode="json"))
        logger.debug("Connection metadata set")

        logger.debug("Updating internal connection tracking")
        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(websocket)
        self._last_heartbeat[websocket] = datetime.now(UTC).timestamp()
        logger.debug("Internal connection tracking updated")

    async def disconnect(self, websocket: WebSocket, user_id: int):
        logger.debug("Starting disconnect for user %s", user_id)
        if user_id in self._connections:
            logger.debug("Found user connections, removing websocket")
            self._connections[user_id].discard(websocket)
            if websocket in self._last_heartbeat:
                del self._last_heartbeat[websocket]
            logger.debug("Removed websocket from internal tracking")

            # Update connection metadata
            meta_key = f"user:{user_id}"
            logger.debug("Getting metadata for key: %s", meta_key)
            if meta := await self.connection_metadata.get(meta_key):
                logger.debug("Found metadata, updating")
                connection_meta = WebSocketConnection.model_validate(meta)
                connection_meta.connection_count -= 1

                if connection_meta.connection_count <= 0:
                    logger.debug("No more connections, cleaning up user data")
                    await self.connection_metadata.delete(meta_key)
                    await self.active_users.remove(user_id)
                else:
                    logger.debug("Updating connection count in metadata")
                    await self.connection_metadata.set(meta_key, connection_meta.model_dump())

            if not self._connections[user_id]:
                logger.debug("No more connections for user, removing from tracking")
                del self._connections[user_id]
        logger.debug("Disconnect complete for user %s", user_id)

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
        await self.disconnect(websocket, user_id)

    async def update_heartbeat(self, websocket: WebSocket):
        """Update last heartbeat time for a connection"""
        logger.debug("Updating heartbeat for websocket")
        current_time = datetime.now(UTC).timestamp()
        self._last_heartbeat[websocket] = current_time
        logger.debug("Updated heartbeat to %s", current_time)

    async def is_connection_alive(self, websocket: WebSocket, timeout_seconds: int = 30) -> bool:
        """Check if a connection is still alive based on its last heartbeat"""
        logger.debug("Checking connection alive status for websocket")
        if websocket not in self._last_heartbeat:
            logger.debug("Websocket not found in heartbeat tracking")
            return False
        last_heartbeat = self._last_heartbeat[websocket]
        current_time = datetime.now(UTC).timestamp()
        is_alive = (current_time - last_heartbeat) < timeout_seconds
        logger.debug(
            "Connection alive check - Last heartbeat: %s, Current time: %s, Difference: %s, Timeout: %s, Is alive: %s",
            last_heartbeat,
            current_time,
            current_time - last_heartbeat,
            timeout_seconds,
            is_alive,
        )
        return is_alive

    async def get_health_info(self) -> dict:
        """Get detailed health information about WebSocket connections"""
        current_time = datetime.now(UTC).timestamp()
        active_connections = sum(len(list(connections)) for connections in self._connections.values())
        dead_connections = sum(1 for ws in self._last_heartbeat if (current_time - self._last_heartbeat[ws]) >= 30)

        return {
            "status": "healthy" if active_connections > 0 and dead_connections == 0 else "degraded",
            "active_users_count": await self.active_users.size(),
            "total_connections": active_connections,
            "dead_connections": dead_connections,
            "connections_by_user": {
                user_id: len(list(connections)) for user_id, connections in self._connections.items()
            },
            "redis_health": await async_redis.health_check(),
            "last_heartbeat_stats": {
                "oldest_heartbeat": min(self._last_heartbeat.values()) if self._last_heartbeat else None,
                "newest_heartbeat": max(self._last_heartbeat.values()) if self._last_heartbeat else None,
                "total_tracked_heartbeats": len(self._last_heartbeat),
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def is_user_connected(self, user_id: int) -> bool:
        """Check if a user has any active connections"""
        logger.debug("Checking if user %s is connected", user_id)
        is_connected = user_id in self._connections and bool(self._connections[user_id])
        logger.debug("User %s connected status: %s", user_id, is_connected)
        return is_connected

    async def get_user_connections(self, user_id: int) -> List[WebSocket]:
        """Get all active connections for a user"""
        logger.debug("Getting connections for user %s", user_id)
        connections = list(self._connections.get(user_id, set()))
        logger.debug("Found %d connections for user %s", len(connections), user_id)
        return connections

    async def close(self) -> None:
        """Close all connections and clean up resources"""
        logger.debug("Starting connection manager cleanup")
        # Close all websocket connections
        for user_id in list(self._connections.keys()):
            logger.debug("Closing connections for user %s", user_id)
            for websocket in list(self._connections[user_id]):
                try:
                    logger.debug("Closing websocket for user %s", user_id)
                    await websocket.close()
                except Exception as e:
                    logger.debug("Error closing websocket: %s", str(e))
                logger.debug("Disconnecting websocket for user %s", user_id)
                await self.disconnect(websocket, user_id)

        # Clear internal state
        logger.debug("Clearing internal state")
        self._connections.clear()
        self._last_heartbeat.clear()

        # Clean up Redis resources
        logger.debug("Cleaning up Redis resources")
        await self.active_users.clear()
        await self.connection_metadata.clear()
        logger.debug("Connection manager cleanup complete")
