import json
import threading

import socketio
from socketio import Namespace
import queue

from runner.gamemodes import Gamemode
from runner.logger import logger
from shared.messages import Connection

sio = socketio.Server()


class SRMWQueue:
    __eof_flag = object()

    def __init__(self):
        self._cv = threading.Condition()
        self._buffer = queue.Queue()
        self._closed = False

    def enqueue(self, v):
        if self._closed:
            return

        with self._cv:
            self._buffer.put(v)
            self._cv.notify_all()

    def close(self):
        self.enqueue(self.__eof_flag)

    def dequeue(self):
        if self._closed:
            return self.__eof_flag

        with self._cv:
            while self._buffer.empty():
                self._cv.wait()

            v = self._buffer.get()

            if v is self.__eof_flag:
                self._closed = True

            return v

    def __next__(self):
        v = self.dequeue()

        if v is self.__eof_flag:
            raise StopIteration()

        return v

    def __iter__(self):
        while True:
            v = self.dequeue()

            if v is self.__eof_flag:
                return

            yield v


class ConnectionThread(threading.Thread):
    def __init__(self, q: SRMWQueue, submissions, send_fn):
        super().__init__()
        self.daemon = True
        self.q = q
        self.submissions = submissions
        self.send_fn = send_fn

    def run(self):
        self.send_fn("aBcDe")
        connection = Connection(lambda m: self.send_fn(m), iter(self.q))
        gamemode, options = Gamemode.get_from_config()
        gamemode.run(self.submissions, options, connections=[connection])


class WebConnection(Namespace):
    def on_connect(self, sid, environ):
        logger.debug("======= Connected")
        q = SRMWQueue()

        with self.session(sid) as session:
            session["web_connection_queue"] = q
            session["web_connection_thread"] = None

    def on_disconnect(self, sid):
        logger.debug("======= Disconnected")
        with self.session(sid) as session:
            session["web_connection_queue"].close()

    def on_start_game(self, sid, data):
        logger.debug("======= Start Game")

        def send_fn(m):
            self.send(m, room=sid)

        with self.session(sid) as session:
            data_obj = json.loads(data)
            t = ConnectionThread(session["web_connection_queue"], data_obj["submissions"], send_fn)
            session["web_connection_thread"] = t
            t.start()

    def on_play_move(self, sid, data):
        logger.debug("======= Play Move")
        with self.session(sid) as session:
            session["web_connection_queue"].enqueue(data)
