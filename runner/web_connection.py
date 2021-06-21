import json
import threading

import socketio
from cuwais.config import config_file
from socketio import Namespace
import queue

from runner.gamemode_runner import Gamemode
from runner.logger import logger
from shared.message_connection import Encoder
from shared.connection import Connection, ConnectionNotActiveError, ConnectionTimedOutError

sio = socketio.Server(async_mode='eventlet')


class SocketConnection(Connection):
    def __init__(self, send_fn):
        self._send_fn = send_fn
        self._semaphore = threading.Semaphore(value=0)
        self._responses = queue.Queue()
        self._closed = False

    def register_response(self, response):
        self._responses.put(response)
        self._semaphore.release()

    def get_next_message_data(self):
        if self._closed:
            raise ConnectionNotActiveError()

        acquired = self._semaphore.acquire(timeout=config_file.get("gamemode.options.player_turn_time"))

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
        result = gamemode.run(self.submissions, options, connections=[self.connection])

        self.send_fn({"type": "result", "result": dict(result)})


def _make_send_fn(connection, sid):
    def send_fn(m):
        connection.send(json.dumps(m, cls=Encoder), room=sid)
    return send_fn


class WebConnection(Namespace):
    def on_connect(self, sid, environ):
        logger.debug(f"Connected {sid}")

        with self.session(sid) as session:
            session["connection"] = SocketConnection(_make_send_fn(self, sid))

    def on_disconnect(self, sid):
        logger.debug(f"Disconnected {sid}")
        with self.session(sid) as session:
            session["connection"].close()

    def on_start_game(self, sid, data):
        logger.debug(f"Start Game {sid}: {data}")

        with self.session(sid) as session:
            data_obj = json.loads(data)

            GamemodeThread(session["connection"], data_obj["submissions"], _make_send_fn(self, sid)).start()

    def on_respond(self, sid, data):
        logger.debug(f"Respond {sid}: {data}")
        with self.session(sid) as session:
            connection: SocketConnection
            connection = session["connection"]
            connection.register_response(data)


sio.register_namespace(WebConnection('/play_game'))
