import time
from typing import Any, Iterable

from runner.logger import logger
from runner.sandbox import TimedContainer, ContainerTimedOutException
from shared.exceptions import FailsafeError
from shared.messages import MessageType


class SubmissionNotActiveError(RuntimeError):
    def __init__(self):
        super(SubmissionNotActiveError, self).__init__()


class ContainerConnection:
    def __init__(self, container: TimedContainer):
        self._connection = container.run()
        self._prints = []
        self._done = False

    @property
    def prints(self):
        return "\n".join(self._prints)

    def get_next_message_data(self):
        """Tries to get a data message from the connection. Raises SubmissionNotActiveError if the container
        is no longer active, or raises ContainerTimedOutException if the container times out while we are reading.
        While these evens are similar, SubmissionNotActiveError is due to the process dying on the VM side
        and ContainerTimedOutException is due to the process dying on the host side"""

        if self._done:
            raise SubmissionNotActiveError()

        for message in self._connection.receive:
            if message.message_type == MessageType.PRINT:
                self._prints.append(message.data)
            elif message.message_type == MessageType.RESULT:
                if isinstance(message.data, FailsafeError):
                    logger.error(str(message.data))
                    raise SubmissionNotActiveError()
                return message.data
            elif message.message_type == MessageType.END:
                self._done = True
                raise SubmissionNotActiveError()

        self._done = True
        self.get_next_message_data()  # Force an except

    def complete(self):
        self._connection.send(MessageType.END)
        messages = []
        while True:
            try:
                data = self.get_next_message_data()
                messages.append(data)
            except (SubmissionNotActiveError, ContainerTimedOutException):
                break
        return messages

    def call(self, method_name, *args, **kwargs) -> Any:
        """Calls a function with name method_name and args and kwargs as given.
        Raises SubmissionNotActiveError if the container is no longer active,
        or raises ContainerTimedOutException if the container times out while we are waiting"""
        self._send("call", method_name=method_name, method_args=args, method_kwargs=kwargs)

        return self.get_next_message_data()

    def ping(self) -> float:
        """Records the time taken for a message to be sent, parsed and responded to.
        Raises SubmissionNotActiveError if the container is no longer active,
        or raises ContainerTimedOutException if the container times out while we are waiting"""
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
            raise SubmissionNotActiveError()

        self._connection.send_result(data)


class Middleware:
    def __init__(self, connections: Iterable[ContainerConnection]):
        self._connections = list(connections)

    @property
    def player_count(self):
        return len(self._connections)

    def complete_all(self):
        return [self._connections[player_id].complete() for player_id in range(self.player_count)]

    def call(self, player_id, method_name, *args, **kwargs) -> Any:
        """Calls a function with name method_name and args and kwargs as given.
        Raises SubmissionNotActiveError if the container is no longer active,
        or raises ContainerTimedOutException if the container times out while we are waiting"""
        return self._connections[player_id].call(method_name, *args, **kwargs)

    def ping(self, player_id) -> float:
        """Records the time taken for a message to be sent, parsed and responded to.
        Raises SubmissionNotActiveError if the container is no longer active,
        or raises ContainerTimedOutException if the container times out while we are waiting"""
        return self._connections[player_id].ping()

    def get_player_prints(self, i):
        return self._connections[i].prints
