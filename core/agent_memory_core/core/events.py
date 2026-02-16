import asyncio
import json
import logging
from typing import Callable, List, Dict, Any, Awaitable

logger = logging.getLogger("agent-memory-core.events")

class MemoryEventEmitter:
    """Internal event bus for real-time notifications."""
    
    def __init__(self):
        self.subscribers: List[Callable[[str, Dict[str, Any]], Awaitable[None]]] = []

    def subscribe(self, callback: Callable[[str, Dict[str, Any]], Awaitable[None]]):
        self.subscribers.append(callback)

    async def emit(self, event_type: str, data: Dict[str, Any]):
        if not self.subscribers:
            return
            
        tasks = [callback(event_type, data) for callback in self.subscribers]
        await asyncio.gather(*tasks, return_exceptions=True)

class PubSubProvider:
    """Interface for multi-instance synchronization (e.g. Redis)."""
    async def publish(self, channel: str, message: Dict[str, Any]):
        raise NotImplementedError

    async def subscribe(self, channel: str, callback: Callable):
        raise NotImplementedError

class RedisPubSubProvider(PubSubProvider):
    """Redis-backed pub/sub for scaling memory across instances."""
    
    def __init__(self, url: str):
        import redis.asyncio as redis
        self.redis = redis.from_url(url)

    async def publish(self, channel: str, message: Dict[str, Any]):
        await self.redis.publish(channel, json.dumps(message))

    async def subscribe(self, channel: str, callback: Callable):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)
        
        async def listen():
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    data = json.loads(message['data'])
                    await callback(data)
        
        asyncio.create_task(listen())
