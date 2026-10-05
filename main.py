import asyncio
import json
import logging
import os
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.runtime import get_runtime
from langgraph.config import get_stream_writer
from langgraph.checkpoint.memory import InMemorySaver
from langchain_mcp_adapters.client import MultiServerMCPClient

from contextlib import asynccontextmanager
from pydantic import BaseModel
import requests
import time
import uuid
from pathlib import Path
import tempfile


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NEURALDEEP_API_KEY = os.environ.get("NEURALDEEP_API_KEY")
if not NEURALDEEP_API_KEY:
    raise ValueError("NEURALDEEP_API_KEY environment variable is not set")


# mcp_client = MultiServerMCPClient(
#     {
#         "math": {
#             "transport": "stdio",
#             "command": "uvx",
#             "args": [
#                 "--cache-dir",
#                 str(Path(tempfile.gettempdir()) / "mcp-uv-cache"),
#                 "mcp-server-calculator",
#             ],
#         },
#     }
# )

# mcp_tools = await mcp_client.get_tools()

agent = None
mcp_client = None
@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, mcp_client

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

    mcp_tools = await mcp_client.get_tools()

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

    yield

model = ChatOpenAI(
    model="qwen3.8-27b",
    openai_api_key="sk-2w7hJXtQKj6KHJ-J9eoYUg",
    openai_api_base="https://api.neuraldeep.ru/v1",
    temperature=0.0,
    streaming=True,
)


class RuntimeContext(BaseModel):
    search_arcanum: Any = None

API_URL = "https://mfphsrdubggjqxvyuzil.supabase.co/functions/v1/knn";
API_KEY = "sb_publishable_XRNtK6CNXu6R2qOwelRE6w_SqIxMsVP";
RETRIES = 2
TIMEOUT = 30
def _search_request(query: str) -> dict:
    """Arcanum search call with retry"""
    last_exc: Exception | None = None

    for attempt in range(RETRIES + 1):
        try:
            res = requests.post(
                API_URL,
                headers={
                    "Content-Type": "application/json",
                    "apikey": API_KEY,
                },
                data=json.dumps({"query": query}),
                timeout=TIMEOUT,
            )
            if not res.ok:
                raise RuntimeError(
                    f"Search failed: {res.status_code} {res.reason}"
                )
            return res.json()
        except Exception as exc:
            if attempt < RETRIES:
                time.sleep(2 ** attempt)


@tool
def search_arcanum(query: str) -> str:
    """Get 5 most relevant arcanum documents for the query"""
    runtime = get_runtime(RuntimeContext)
    writer = get_stream_writer()

    writer(f"Looking up relevant documents for query: {query}")

    try:
        response = runtime.context.search_arcanum(query)

        writer(f"Acquired relevant documents: {len(response["results"])}")
        for document in response["results"]:
          writer(f"<a href=\"{document["url"]}\">{document["title"]}</a>")

        return response
    except Exception as e:
        return f"Error: {e}"


# agent = create_agent(
#     model=model,
#     tools=[search_arcanum],
#     system_prompt=(
#         "You are a helpful assistant specialized in the game "
#         "Arcanum of Steamworks and Magic Obscura. "
#         "If you are uncertain about the user query, "
#         "use tool 'search_arcanum(query)'"
#     ),
#     context_schema=RuntimeContext,
#     checkpointer=InMemorySaver(),
# )


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")


manager = ConnectionManager()
app = FastAPI(lifespan=lifespan)


async def send_json(websocket: WebSocket, payload: dict):
    """Отправка JSON-сообщения клиенту."""
    await websocket.send_text(json.dumps(payload, ensure_ascii=False))


async def run_agent_streaming(websocket: WebSocket, question: str, thread_id):
    """Запускает агента в режиме astream и стримит события в WebSocket."""

    config = {"configurable": {"thread_id": thread_id}}

    max_retries = 3
    for attempt in range(max_retries):
        try:
            async for mode, data in agent.astream(
                {"messages": question},
                config,
                stream_mode=["messages", "custom"],
                context=RuntimeContext(search_arcanum=_search_request),
            ):
                if mode == "messages":
                    chunk, metadata = data

                    if "\"results\"" in chunk.content: # hide from user raw seach result
                        continue

                    if chunk.content:
                        await send_json(
                            websocket,
                            {
                                "type": "token",
                                "content": chunk.content,
                            },
                        )

                if mode == "custom":
                    await send_json(
                        websocket,
                        {
                            "type": "tool_message",
                            "content": data,
                        },
                    )

            await send_json(websocket, {"type": "done"})
            return

        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Retry {attempt + 1}/{max_retries}")
                await send_json(
                    websocket,
                    {"type": "retry", "attempt": attempt + 1, "max": max_retries},
                )
                await asyncio.sleep(2 ** attempt)
                continue

            logger.exception("Agent execution failed")
            await send_json(
                websocket,
                {"type": "error", "error": str(e)},
            )
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

            thread_id = payload.get("thread_id", "")
            if not thread_id:
                thread_id = str(uuid.uuid4())

            await send_json(websocket, {"type": "start", "question": question, "thread_id": thread_id})

            await run_agent_streaming(websocket, question, thread_id)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("Unexpected WebSocket error")
        manager.disconnect(websocket)
