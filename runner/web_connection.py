import json
import threading

import socketio
from socketio import Namespace
import queue

from runner.gamemodes import Gamemode
from runner.logger import logger
from shared.messages import Connection, MessageType

sio = socketio.Server()


class SRMWQueue:
    __eof_flag = object()

    def __init__(self):
        self._buffer = queue.Queue()
        self._count = threading.Semaphore(value=0)
        self._closed = False

    def enqueue(self, v):
        if self._closed:
            return

        logger.debug(f"Enqueued {v}")

        self._buffer.put(v)
        self._count.release()

    def close(self):
        self.enqueue(self.__eof_flag)
        self._count.release(2 << 32)  # Unblock anything blocked

    def dequeue(self):
        if self._closed:
            return self.__eof_flag

        logger.debug(f"Dequeuing {self._count} {self._buffer}")

        self._count.acquire()

        # Check again because we just blocked
        if self._closed:
            return self.__eof_flag

        v = self._buffer.get()

        if v is self.__eof_flag:
            self._closed = True

        logger.debug(f"Dequeued {v}")

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


class SendThread(threading.Thread):
    def __init__(self, messages, send_fn):
        super().__init__()
        self.daemon = True
        self.messages = messages
        self.send_fn = send_fn

    def run(self):
        for message in self.messages:
            self.send_fn(message)


class GamemodeThread(threading.Thread):
    def __init__(self, in_queue: SRMWQueue, out_queue: SRMWQueue, submissions):
        super().__init__()
        self.daemon = True
        self.in_queue = in_queue
        self.out_queue = out_queue
        self.submissions = submissions

    def run(self):
        connection = Connection(lambda m: self.out_queue.enqueue(m), iter(self.in_queue))
        gamemode, options = Gamemode.get_from_config()
        gamemode.run(self.submissions, options, connections=[connection])


class WebConnection(Namespace):
    def on_connect(self, sid, environ):
        logger.debug("======= Connected")

        listening_queue = SRMWQueue()
        sending_queue = SRMWQueue()

        with self.session(sid) as session:
            session["web_connection_listening_queue"] = listening_queue
            session["web_connection_sending_queue"] = sending_queue
            session["web_connection_connection"] = None

    def on_disconnect(self, sid):
        logger.debug("======= Disconnected")
        with self.session(sid) as session:
            session["web_connection_listening_queue"].close()
            session["web_connection_sending_queue"].close()

            connection = session["web_connection_connection"]
            if connection is not None:
                connection.send(MessageType.END)

    def on_start_game(self, sid, data):
        logger.debug("======= Start Game")

        def send_fn(m):
            self.send(m, room=sid)

        with self.session(sid) as session:
            data_obj = json.loads(data)

            listening_queue = session["web_connection_listening_queue"]
            sending_queue = session["web_connection_sending_queue"]

            GamemodeThread(listening_queue, sending_queue, data_obj["submissions"]).start()

            connection = Connection(lambda m: listening_queue.enqueue(m), iter(sending_queue))
            session["web_connection_connection"] = connection

            SendThread(connection.receive, send_fn)

    def on_new_key(self, sid, data):
        logger.debug("======= Play Move")
        with self.session(sid) as session:
            connection: Connection
            connection = session["web_connection_connection"]
            connection.send_result(data)
