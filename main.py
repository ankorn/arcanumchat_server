import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
import tempfile
from typing import Any

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.runtime import get_runtime
from langgraph.config import get_stream_writer
from langgraph.checkpoint.memory import InMemorySaver
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from pydantic import BaseModel
from uvicorn.protocols.utils import ClientDisconnected

from _search_request import _search_request

logging.getLogger("httpx").setLevel(logging.INFO)

NEURALDEEP_API_KEY_2 = os.environ.get("NEURALDEEP_API_KEY_2")
if not NEURALDEEP_API_KEY_2:
    raise ValueError("NEURALDEEP_API_KEY_2 environment variable is not set")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

TIMEOUT = 60

_timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
_limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)

model = ChatOpenAI(
    model="qwen3.6-35b-a3b",
    openai_api_key=NEURALDEEP_API_KEY_2,
    openai_api_base="https://api.neuraldeep.ru/v1",
    temperature=0.0,
    streaming=True,
    http_client=httpx.Client(timeout=_timeout, limits=_limits),
    http_async_client=httpx.AsyncClient(timeout=_timeout, limits=_limits),
    max_retries=3,
)

agent = None
http_client: httpx.AsyncClient | None = None

class RuntimeContext(BaseModel):
    search_request: Any = None

@tool
async def search_arcanum(query: str) -> str:
    """Get 5 most relevant arcanum documents for the query"""
    runtime = get_runtime(RuntimeContext)
    writer = get_stream_writer()

    writer(f"Looking up relevant documents for query: {query}")

    t0 = time.monotonic()
    try:
        response = await runtime.context.search_request(query, http_client, logger)
        elapsed = time.monotonic() - t0
        logger.info("tool search_arcanum ok in %.2fs", elapsed)

        writer("Acquired relevant documents:")
        for document in response["results"]:
            writer(
                f'<a href="{document["url"]}" target="_blank" '
                f'rel="noopener noreferrer">{document["title"]}</a>'
            )

        return json.dumps(response, ensure_ascii=False)
    except Exception as e:
        logger.error("tool search_arcanum failed after %.2fs: %s",
                     time.monotonic() - t0, e)
        return f"Error: {e}"

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, http_client

    http_client = httpx.AsyncClient(timeout=TIMEOUT)
    try:
        mcp_client = MultiServerMCPClient(
            {
                "math": {
                    "transport": "stdio",
                    "command": "uvx",
                    "args": [
                        "--cache-dir",
                        str(Path(tempfile.gettempdir()) / "mcp-uv-cache"),
                        "mcp-server-calculator",
                    ],
                },
            }
        )

        async with AsyncExitStack() as mcp_stack:
            session = await mcp_stack.enter_async_context(
                mcp_client.session("math")
            )
            mcp_tools = await load_mcp_tools(session)
            logger.info("Loaded %d MCP tools from persistent session", len(mcp_tools))

            agent = create_agent(
                model=model,
                tools=[search_arcanum, *mcp_tools],
                system_prompt=(
                    "You are a helpful assistant specialized in the game "
                    "Arcanum of Steamworks and Magic Obscura. "
                    "If you are uncertain about the user query, "
                    "use tool 'search_arcanum(query)'"
                ),
                context_schema=RuntimeContext,
                checkpointer=InMemorySaver(),
            )

            logger.info("Agent ready")
            try:
                yield
            finally:
                logger.info("Lifespan: shutting down")
    finally:
        if http_client is not None:
            await http_client.aclose()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("Client connected. Total: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("Client disconnected. Total: %d", len(self.active_connections))


manager = ConnectionManager()
app = FastAPI(lifespan=lifespan)


async def send_json(websocket: WebSocket, payload: dict) -> bool:
    try:
        await websocket.send_text(json.dumps(payload, ensure_ascii=False))
        return True
    except ClientDisconnected:
        logger.warning("send_json: client disconnected")
        return False


async def run_agent_streaming(websocket: WebSocket, question: str, thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}

    max_retries = 3
    t_start = time.monotonic()
    first_token_at: float | None = None
    token_count = 0

    for attempt in range(max_retries):
        try:
            async for mode, data in agent.astream(
                {"messages": question},
                config,
                stream_mode=["messages", "custom"],
                context=RuntimeContext(search_request=_search_request),
            ):
                if mode == "messages":
                    chunk, metadata = data

                    if chunk.__class__.__name__ == "ToolMessage":
                        ok = await send_json(websocket, {
                            "type": "tool_result",
                            "name": getattr(chunk, "name", None),
                            "content": chunk.content,
                        })
                        if not ok:
                            return
                        continue

                    if chunk.content:
                        if first_token_at is None:
                            first_token_at = time.monotonic()
                            logger.info(
                                "first token after %.2fs (thread=%s)",
                                first_token_at - t_start, thread_id,
                            )
                        token_count += 1
                        ok = await send_json(websocket, {
                            "type": "token",
                            "content": chunk.content,
                        })
                        if not ok:
                            return

                if mode == "custom":
                    ok = await send_json(websocket, {
                        "type": "tool_message",
                        "content": data,
                    })
                    if not ok:
                        return

            total = time.monotonic() - t_start
            logger.info(
                "agent finished in %.2fs (%d tokens, thread=%s)",
                total, token_count, thread_id,
            )
            await send_json(websocket, {"type": "done"})
            return

        except ClientDisconnected:
            logger.warning("client disconnected mid-run (thread=%s)", thread_id)
            return

        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    "Retry %d/%d after %.2fs: %s",
                    attempt + 1, max_retries,
                    time.monotonic() - t_start, e,
                )
                if not await send_json(websocket, {
                    "type": "retry",
                    "attempt": attempt + 1,
                    "max": max_retries,
                }):
                    return
                await asyncio.sleep(2 ** attempt)
                continue

            logger.exception("Agent execution failed (thread=%s)", thread_id)
            await send_json(websocket, {"type": "error", "error": str(e)})
            return


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await send_json(websocket, {"type": "error", "error": "Invalid JSON"})
                continue

            question = payload.get("question", "").strip()
            if not question:
                await send_json(websocket, {"type": "error", "error": "Empty question"})
                continue

            thread_id = payload.get("thread_id", "") or str(uuid.uuid4())

            await send_json(websocket, {
                "type": "start",
                "question": question,
                "thread_id": thread_id,
            })

            await run_agent_streaming(websocket, question, thread_id)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally")
    except ClientDisconnected:
        logger.info("WebSocket client disconnected")
    except Exception:
        logger.exception("Unexpected WebSocket error")
    finally:
        manager.disconnect(websocket)
