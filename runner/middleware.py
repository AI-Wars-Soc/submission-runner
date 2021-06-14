import time
from typing import Any, Iterable

from runner.logger import logger
from runner.sandbox import TimedContainer, ContainerTimedOutException
from shared.exceptions import FailsafeError
from shared.messages import MessageType, HandshakeFailedError


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

    def send_message(self, data):
        if self._done:
            raise SubmissionNotActiveError()

        self._connection.send_result(data)

    def send_end(self):
        self._connection.send(MessageType.END)


class ContainerConnectionFailedError(RuntimeError):
    def __init__(self, i, prints):
        super().__init__()
        self.container_index = i
        self.prints = prints


class Middleware:
    def __init__(self, containers: Iterable[TimedContainer]):
        self._connections = []
        for i, container in enumerate(containers):
            try:
                self._connections.append(ContainerConnection(container))
            except HandshakeFailedError as e:
                raise ContainerConnectionFailedError(i, e.prints)

    @property
    def player_count(self):
        return len(self._connections)

    def complete_all(self):
        self._send_ends()
        messages = []
        for player_id in range(self.player_count):
            new_messages = []
            while True:
                try:
                    data = self._connections[player_id].get_next_message_data()
                    new_messages.append(data)
                except (SubmissionNotActiveError, ContainerTimedOutException):
                    break
            messages.append(new_messages)
        return messages

    def call(self, player_id, method_name, *args, **kwargs) -> Any:
        """Calls a function with name method_name and args and kwargs as given.
        Raises SubmissionNotActiveError if the container is no longer active,
        or raises ContainerTimedOutException if the container times out while we are waiting"""
        self._send(player_id, "call", method_name=method_name, method_args=args, method_kwargs=kwargs)

        return self._connections[player_id].get_next_message_data()

    def send_data(self, player_id, **kwargs) -> None:
        self._send(player_id, "data", **kwargs)

    def ping(self, player_id) -> float:
        """Records the time taken for a message to be sent, parsed and responded to.
        Raises SubmissionNotActiveError if the container is no longer active,
        or raises ContainerTimedOutException if the container times out while we are waiting"""
        start_time = time.time_ns()
        self._send(player_id, "ping")

        self._connections[player_id].get_next_message_data()
        end_time = time.time_ns()

        return (end_time - start_time) / 1e9

    def _send_ends(self):
        for player_id in range(self.player_count):
            self._connections[player_id].send_end()

    def get_player_prints(self, i):
        return self._connections[i].prints

    def _send(self, player_id, instruction, **kwargs):
        self._connections[player_id].send_message({"type": instruction, **kwargs})
