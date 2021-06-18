import json
import threading

import socketio
from socketio import Namespace
import queue

from runner.gamemodes import Gamemode
from runner.logger import logger
from shared.message_connection import Encoder
from shared.connection import Connection, ConnectionNotActiveError, ConnectionTimedOutError

sio = socketio.Server()


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
        acquired = self._semaphore.acquire(timeout=5*60)

        if not acquired:
            self.close()
            raise ConnectionTimedOutError()

        if self._closed:
            self._semaphore.release()
            raise ConnectionNotActiveError()

        self._responses.get()

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
    def __init__(self, connection, submissions):
        super().__init__()
        self.daemon = True
        self.connection = connection
        self.submissions = submissions

    def run(self):
        gamemode, options = Gamemode.get_from_config()
        result = gamemode.run(self.submissions, options, connections=[self.connection])

        logger.debug(f"Completed game, got result {dict(result)}")


class WebConnection(Namespace):
    def on_connect(self, sid, environ):
        logger.debug("======= Connected")

        def send_fn(m):
            self.send(json.dumps(m, cls=Encoder), room=sid)

        with self.session(sid) as session:
            session["connection"] = SocketConnection(send_fn)

    def on_disconnect(self, sid):
        logger.debug("======= Disconnected")
        with self.session(sid) as session:
            session["connection"].close()

    def on_start_game(self, sid, data):
        logger.debug("======= Start Game")

        with self.session(sid) as session:
            data_obj = json.loads(data)

            GamemodeThread(session["connection"], data_obj["submissions"]).start()

    def on_respond(self, sid, data):
        logger.debug("======= Respond")
        with self.session(sid) as session:
            connection: SocketConnection
            connection = session["connection"]
            connection.register_response(data)
