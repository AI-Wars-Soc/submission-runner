import asyncio
import time
from asyncio import wait_for
from contextlib import asynccontextmanager
from typing import Coroutine

from runner.logger import logger
from shared.connection import Connection, ConnectionTimedOutError


class TimedConnection(Connection):
    """
    Wraps a connection in a timer that raises ConnectionTimedOutError after all
    operations took over some given time
    """
    def __init__(self, connection: Connection, timeout: float):
        self._connection = connection
        self._time_remaining = timeout

    @asynccontextmanager
    async def _timed(self, task: Coroutine):
        start = time.time()
        try:
            logger.debug(f"Connection {self._connection}: Time remaining: {self._time_remaining}, running {task}")
            yield await wait_for(task, self._time_remaining)
        except asyncio.TimeoutError:
            logger.debug(f"Connection {self._connection}: Timeout")
            while True:
                raise ConnectionTimedOutError()
        end = time.time()
        self._time_remaining -= (end - start)

    def get_prints(self) -> str:
        return self._connection.get_prints()

    async def get_next_message_data(self):
        async with self._timed(self._connection.get_next_message_data()) as res:
            return res

    async def close(self):
        async with self._timed(self._connection.close()) as res:
            return res

    async def send_call(self, method_name, method_args, method_kwargs):
        async with self._timed(self._connection.send_call(method_name, method_args, method_kwargs)) as res:
            return res

    async def send_ping(self):
        async with self._timed(self._connection.send_ping()) as res:
            return res
