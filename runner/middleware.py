from typing import Any, Iterable

from runner.sandbox import TimedContainer
from shared.messages import MessageType


class SubmissionNotActiveError(RuntimeError):
    def __init__(self):
        super(SubmissionNotActiveError, self).__init__()


class ContainerConnection:
    def __init__(self, script_name: str, container: TimedContainer, env_vars):
        self._connection = container.run(script_name, env_vars)
        self._prints = []
        self._done = False

    @property
    def prints(self):
        return "\n".join(self._prints)

    def get_next_message_data(self):
        if self._done:
            raise SubmissionNotActiveError()

        for message in self._connection.receive:
            if message.message_type == MessageType.PRINT:
                self._prints.append(message.data)
            elif message.message_type == MessageType.RESULT:
                print(f"Middleware got message data {message}", flush=True)
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


class Middleware:
    def __init__(self, script_name: str, containers: Iterable[TimedContainer], env_vars):
        self._connections = [ContainerConnection(script_name, container, env_vars) for container in containers]

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
                    print(f"Middleware got result {data}", flush=True)
                    new_messages.append(data)
                except SubmissionNotActiveError:
                    break
            print(f"Middleware got results {new_messages}", flush=True)
            messages.append(new_messages)
        return messages

    def call(self, player_id, method_name, *args, **kwargs) -> Any:
        self._send(player_id, "call", method_name=method_name, method_args=args, method_kwargs=kwargs)

        return self._connections[player_id].get_next_message_data()

    def send_data(self, player_id, **kwargs) -> None:
        self._send(player_id, "data", **kwargs)

    def _send_ends(self):
        for player_id in range(self.player_count):
            self._connections[player_id].send_end()

    def get_player_prints(self, i):
        return self._connections[i].prints

    def _send(self, player_id, instruction, **kwargs):
        self._connections[player_id].send_message({"type": instruction, **kwargs})
