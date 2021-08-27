import asyncio
import json
import threading
from json import JSONDecodeError

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
    def __init__(self, send_fn):
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
            self.close()
            raise ConnectionTimedOutError()

        if self._closed:
            self._semaphore.release()
            raise ConnectionNotActiveError()

        return self._responses.get()

    def close(self):
        self._closed = True
        self._semaphore.release()

    def send_call(self, method_name, method_args, method_kwargs):
        self._send_fn({"type": "call", "name": method_name, "args": method_args, "kwargs": method_kwargs})

    def send_ping(self):
        self._send_fn({"type": "ping"})

    def get_prints(self) -> str:
        return ""


class GamemodeThread(threading.Thread):
    def __init__(self, connection, submissions, send_fn):
        super().__init__()
        self.daemon = True
        self.connection = connection
        self.submissions = submissions
        self.send_fn = send_fn

    def run(self):
        gamemode, options = Gamemode.get_from_config()
        options["turn_time"] = config_file.get("gamemode.options.player_turn_time")
        result = gamemode_runner.run(gamemode, self.submissions, options, connections=[self.connection])

        self.send_fn({"type": "result", "result": dict(result)})


def _make_send_fn(websocket: WebSocket):
    async def send_fn(m):
        await websocket.send_text(json.dumps(m, cls=Encoder))
    return send_fn


async def websocket_game(websocket: WebSocket):
    connection = SocketConnection(_make_send_fn(websocket))

    async def disconnect():
        connection.close()
        await websocket.close()

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

    GamemodeThread(connection, data["submissions"], _make_send_fn(websocket)).start()

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

    await disconnect()
