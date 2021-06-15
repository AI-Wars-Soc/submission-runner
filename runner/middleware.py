import time
from typing import Any, Iterable

from runner.logger import logger
from shared.exceptions import FailsafeError
from shared.messages import MessageType, Connection


class ConnectionNotActiveError(RuntimeError):
    def __init__(self):
        super(ConnectionNotActiveError, self).__init__()


class ConnectionTimedOutError(RuntimeError):
    def __init__(self, container):
        self.container = container
        super().__init__()


class PlayerConnection:
    def __init__(self, connection: Connection):
        self._connection = connection
        self._prints = []
        self._done = False

    @property
    def prints(self):
        return "\n".join(self._prints)

    def get_next_message_data(self):
        """Tries to get a data message from the connection. Raises ConnectionNotActiveError if the container
        is no longer active, or raises ConnectionTimedOutError if the container times out while we are reading.
        While these evens are similar, ConnectionNotActiveError is due to the process dying on the VM side
        and ConnectionTimedOutError is due to the process dying on the host side"""

        if self._done:
            raise ConnectionNotActiveError()

        for message in self._connection.receive:
            if message.message_type == MessageType.PRINT:
                self._prints.append(message.data)
            elif message.message_type == MessageType.RESULT:
                if isinstance(message.data, FailsafeError):
                    logger.error(str(message.data))
                    self._done = True
                    raise ConnectionNotActiveError()
                return message.data
            elif message.message_type == MessageType.END:
                self._done = True
                raise ConnectionNotActiveError()

        self._done = True
        self.get_next_message_data()  # Force an except

    def complete(self):
        self._connection.send(MessageType.END)
        messages = []
        while True:
            try:
                data = self.get_next_message_data()
                messages.append(data)
            except (ConnectionNotActiveError, ConnectionTimedOutError):
                break
        return messages

    def call(self, method_name, *args, **kwargs) -> Any:
        """Calls a function with name method_name and args and kwargs as given.
        Raises ConnectionNotActiveError if the container is no longer active,
        or raises ConnectionTimedOutError if the container times out while we are waiting"""
        self._send("call", method_name=method_name, method_args=args, method_kwargs=kwargs)

        return self.get_next_message_data()

    def ping(self) -> float:
        """Records the time taken for a message to be sent, parsed and responded to.
        Raises ConnectionNotActiveError if the container is no longer active,
        or raises ConnectionTimedOutError if the container times out while we are waiting"""
        start_time = time.time_ns()
        self._send("ping")

        self.get_next_message_data()
        end_time = time.time_ns()

        delta = (end_time - start_time) / 1e9

        logger.debug(f"Ping delta: {delta}")

        return delta

    def _send(self, instruction, **kwargs):
        self._send_message({"type": instruction, **kwargs})

    def _send_message(self, data):
        if self._done:
            raise ConnectionNotActiveError()

        self._connection.send_result(data)


class Middleware:
    def __init__(self, connections: Iterable[PlayerConnection]):
        self._connections = list(connections)

    @property
    def player_count(self):
        return len(self._connections)

    def complete_all(self):
        return [self._connections[player_id].complete() for player_id in range(self.player_count)]

    def call(self, player_id, method_name, *args, **kwargs) -> Any:
        """Calls a function with name method_name and args and kwargs as given.
        Raises ConnectionNotActiveError if the container is no longer active,
        or raises ConnectionTimedOutError if the container times out while we are waiting"""
        return self._connections[player_id].call(method_name, *args, **kwargs)

    def ping(self, player_id) -> float:
        """Records the time taken for a message to be sent, parsed and responded to.
        Raises ConnectionNotActiveError if the container is no longer active,
        or raises ConnectionTimedOutError if the container times out while we are waiting"""
        return self._connections[player_id].ping()

    def get_player_prints(self, i):
        return self._connections[i].prints
