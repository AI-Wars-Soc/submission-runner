import abc
import logging
import time
from typing import Any


class Connection:
    @abc.abstractmethod
    def get_prints(self) -> str:
        pass

    @abc.abstractmethod
    def get_next_message_data(self):
        """Tries to get a data message from the connection. Raises ConnectionNotActiveError if the container
        is no longer active, or raises ConnectionTimedOutError if the container times out while we are reading.
        While these evens are similar, ConnectionNotActiveError is due to the process dying on the VM side
        and ConnectionTimedOutError is due to the process dying on the host side"""
        pass

    @abc.abstractmethod
    def close(self):
        pass

    def complete(self):
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
        self.send_call(method_name=method_name, method_args=args, method_kwargs=kwargs)

        return self.get_next_message_data()

    def ping(self) -> float:
        """Records the time taken for a message to be sent, parsed and responded to.
        Raises ConnectionNotActiveError if the container is no longer active,
        or raises ConnectionTimedOutError if the container times out while we are waiting"""
        start_time = time.time_ns()
        self.send_ping()

        self.get_next_message_data()
        end_time = time.time_ns()

        delta = (end_time - start_time) / 1e9

        logging.debug(f"Ping delta: {delta}")

        return delta

    @abc.abstractmethod
    def send_call(self, method_name, method_args, method_kwargs):
        pass

    @abc.abstractmethod
    def send_ping(self):
        pass


class ConnectionNotActiveError(RuntimeError):
    def __init__(self):
        super(ConnectionNotActiveError, self).__init__()


class ConnectionTimedOutError(RuntimeError):
    def __init__(self):
        super().__init__()
