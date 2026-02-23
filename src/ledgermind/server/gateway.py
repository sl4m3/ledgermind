import logging
import asyncio
import os
import json
from fastapi import FastAPI, HTTPException, Header, Depends, WebSocket, WebSocketDisconnect, Security
from fastapi.security.api_key import APIKeyHeader, APIKey
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from ledgermind.core.api.memory import Memory
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger("agent_memory_gateway")
app = FastAPI(title="Agent Memory REST & Real-time Gateway")

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

memory_instance: Optional[Memory] = None

class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    offset: int = 0
    namespace: str = "default"
    mode: str = "balanced"

class RecordRequest(BaseModel):
    title: str
    target: str
    rationale: str
    consequences: Optional[List[str]] = []
    namespace: str = "default"

async def get_api_key(api_key_header: str = Security(api_key_header)):
    expected_key = os.environ.get("LEDGERMIND_API_KEY")
    if not expected_key:
        return None
    if api_key_header == expected_key:
        return api_key_header
    raise HTTPException(status_code=403, detail="Could not validate credentials")

def get_memory():
    if memory_instance is None:
        raise HTTPException(status_code=500, detail="Memory not initialized")
    return memory_instance

@app.post("/search", dependencies=[Depends(get_api_key)])
async def search(req: SearchRequest, mem: Memory = Depends(get_memory)):
    results = mem.search_decisions(req.query, limit=req.limit, mode=req.mode)
    return {"status": "success", "results": results}

@app.post("/record", dependencies=[Depends(get_api_key)])
async def record(req: RecordRequest, mem: Memory = Depends(get_memory)):
    try:
        res = mem.record_decision(
            title=req.title, target=req.target, 
            rationale=f"[via REST] {req.rationale}", 
            consequences=req.consequences
        )
        return {"status": "success", "id": res.metadata.get("file_id")}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/events")
async def sse_events(mem: Memory = Depends(get_memory)):
    """Streaming endpoint for memory updates (SSE)."""
    async def event_generator():
        queue = asyncio.Queue()
        
        async def on_change(event_type, data):
            await queue.put({"event": event_type, "data": data})
            
        mem.events.subscribe(on_change)
        
        while True:
            change = await queue.get()
            yield {
                "event": change["event"],
                "data": json.dumps(change["data"])
            }

    return EventSourceResponse(event_generator())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, mem: Memory = Depends(get_memory)):
    """Bi-directional live updates via WebSockets."""
    await websocket.accept()
    
    async def on_change(event_type, data):
        try:
            await websocket.send_json({"event": event_type, "data": data})
        except: pass # Connection might be closed

    mem.events.subscribe(on_change)
    
    try:
        while True:
            # Handle incoming commands via WS if needed
            data = await websocket.receive_text()
            await websocket.send_json({"status": "received", "echo": data})
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")

@app.get("/health")
async def health():
    return {"status": "alive"}

def run_gateway(memory: Memory, host: str = "0.0.0.0", port: int = 8000): # nosec B104
    global memory_instance
    memory_instance = memory
    import uvicorn
    uvicorn.run(app, host=host, port=port)
