import asyncio
import json
from json import JSONDecodeError
from typing import Callable, Awaitable

from cuwais.config import config_file
import queue

from starlette.websockets import WebSocketDisconnect

from runner import gamemode_runner
from runner.gamemode_runner import Gamemode
from runner.logger import logger
from shared.message_connection import Encoder, Decoder
from shared.connection import Connection, ConnectionNotActiveError, ConnectionTimedOutError
from fastapi import WebSocket


class SocketConnection(Connection):
    def __init__(self, send_fn: Callable[[dict], Awaitable]):
        self._send_fn = send_fn
        self._semaphore = asyncio.Semaphore(value=0)
        self._responses = queue.Queue()
        self._closed = False

    def register_response(self, response):
        self._responses.put(response)
        self._semaphore.release()

    async def get_next_message_data(self):
        if self._closed:
            raise ConnectionNotActiveError()

        acquired = await self._semaphore.acquire()

        if not acquired:
            await self.close()
            raise ConnectionTimedOutError()

        if self._closed:
            self._semaphore.release()
            raise ConnectionNotActiveError()

        return self._responses.get()

    async def close(self):
        self._closed = True
        self._semaphore.release()

    async def send_call(self, method_name, method_args, method_kwargs):
        await self._send_fn({"type": "call", "name": method_name, "args": method_args, "kwargs": method_kwargs})

    async def send_ping(self):
        await self._send_fn({"type": "ping"})

    def get_prints(self) -> str:
        return ""


def _make_send_fn(websocket: WebSocket):
    async def send_fn(m):
        await websocket.send_text(json.dumps(m, cls=Encoder))
    return send_fn


async def _run_game_coroutine(submissions, connection, send_fn):
    gamemode, options = Gamemode.get_from_config()
    options["turn_time"] = config_file.get("gamemode.options.player_turn_time")
    result = await gamemode_runner.run(gamemode, submissions, options, connections=[connection])

    send_fn({"type": "result", "result": dict(result)})


async def _websocket_connection_coroutine(websocket, connection, disconnect):
    while True:
        try:
            data = await websocket.receive_text()
        except WebSocketDisconnect:
            break

        # Decode data and check validity
        try:
            data = json.loads(data, cls=Decoder)
        except json.JSONDecodeError:
            await disconnect()
            return

        if "value" not in data:
            await disconnect()
            return

        data = data["value"]
        connection.register_response(data)


async def websocket_game(websocket: WebSocket):
    await websocket.accept()
    connection = SocketConnection(_make_send_fn(websocket))

    async def disconnect():
        await connection.close()
        await websocket.close()

    try:
        try:
            data = await websocket.receive_json()
        except JSONDecodeError:
            await websocket.send_text(json.dumps({"error": "Invalid JSON data"}, cls=Encoder))
            return
        logger.debug(f"Start Game: {data}")

        if "submissions" not in data:
            await disconnect()
            return

        if not all(isinstance(s, str) for s in data):
            await disconnect()
            return

        game_task = asyncio.create_task(_run_game_coroutine(data["submissions"], connection, _make_send_fn(websocket)))
        connection_task = asyncio.create_task(_websocket_connection_coroutine(websocket, connection, disconnect))
        await asyncio.gather(game_task, connection_task)
    finally:
        await disconnect()
