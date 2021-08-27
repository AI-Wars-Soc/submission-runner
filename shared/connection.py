import abc
import logging
import time
from typing import Any


class Connection:
    @abc.abstractmethod
    def get_prints(self) -> str:
        pass

    @abc.abstractmethod
    async def get_next_message_data(self):
        """Tries to get a data message from the connection. Raises ConnectionNotActiveError if the container
        is no longer active, or raises ConnectionTimedOutError if the container times out while we are reading.
        While these evens are similar, ConnectionNotActiveError is due to the process dying on the VM side
        and ConnectionTimedOutError is due to the process dying on the host side"""
        pass

    @abc.abstractmethod
    async def close(self):
        pass

    async def complete(self):
        await self.close()
        messages = []
        while True:
            try:
                data = await self.get_next_message_data()
                messages.append(data)
            except (ConnectionNotActiveError, ConnectionTimedOutError):
                break
        return messages

    async def call(self, method_name, *args, **kwargs) -> Any:
        """Calls a function with name method_name and args and kwargs as given.
        Raises ConnectionNotActiveError if the container is no longer active,
        or raises ConnectionTimedOutError if the container times out while we are waiting"""
        await self.send_call(method_name=method_name, method_args=args, method_kwargs=kwargs)

        return await self.get_next_message_data()

    async def ping(self) -> float:
        """Records the time taken for a message to be sent, parsed and responded to.
        Raises ConnectionNotActiveError if the container is no longer active,
        or raises ConnectionTimedOutError if the container times out while we are waiting"""
        start_time = time.time_ns()
        await self.send_ping()

        await self.get_next_message_data()
        end_time = time.time_ns()

        delta = (end_time - start_time) / 1e9

        logging.debug(f"Ping delta: {delta}")

        return delta

    @abc.abstractmethod
    async def send_call(self, method_name, method_args, method_kwargs):
        pass

    @abc.abstractmethod
    async def send_ping(self):
        pass


class ConnectionNotActiveError(RuntimeError):
    def __init__(self):
        super(ConnectionNotActiveError, self).__init__()


class ConnectionTimedOutError(RuntimeError):
    def __init__(self):
        super().__init__()
