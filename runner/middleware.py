from typing import Any, Iterable

from runner.sandbox import TimedContainer
from shared.messages import Message, MessageType, MessageInputStream


class SubmissionNotActiveError(RuntimeError):
    def __init__(self):
        super(SubmissionNotActiveError, self).__init__()


class SubmissionEndWithError(RuntimeError):
    def __init__(self, final_message: Message):
        super(SubmissionEndWithError, self).__init__(str(final_message.message_type.value))


class ContainerConnection:
    def __init__(self, script_name: str, container: TimedContainer, env_vars):
        self._input_stream = MessageInputStream()
        self._output_stream = container.run(script_name, self._input_stream, env_vars)
        self._prints = []
        self._done = False

    @property
    def prints(self):
        return "\n".join(self._prints)

    def get_next_message_data(self):
        if self._done:
            raise SubmissionNotActiveError()

        for message in self._output_stream:
            if message.message_type == MessageType.PRINT:
                self._prints.append(message.data["str"])
            elif message.message_type == MessageType.RESULT:
                return message.data
            elif message.is_error():
                self._done = True
                raise SubmissionEndWithError(message)
            elif message.is_end():
                self._done = True
                raise SubmissionNotActiveError()

        self._done = True
        self.get_next_message_data()  # Force an except

    def send_message(self, data):
        if self._done:
            raise SubmissionNotActiveError()

        self._input_stream.send(Message.new_result(data))


class Middleware:
    def __init__(self, script_name: str, containers: Iterable[TimedContainer], env_vars):
        self._connections = [ContainerConnection(script_name, container, env_vars) for container in containers]

    @property
    def player_count(self):
        return len(self._connections)

    def complete_all(self):
        messages = []
        for player_id in range(self.player_count):
            new_messages = []
            while True:
                try:
                    data = self._connections[player_id].get_next_message_data()
                    new_messages.append(data)
                except SubmissionNotActiveError:
                    break
            messages.append(new_messages)
        return messages

    def call(self, player_id, method_name, *args, **kwargs) -> Any:
        self._send(player_id, "call", method_name=method_name, method_args=args, method_kwargs=kwargs)

        return self._connections[player_id].get_next_message_data()

    def send_data(self, player_id, **kwargs) -> Any:
        self._send(player_id, "data", **kwargs)

        return self._connections[player_id].get_next_message_data()

    def get_player_prints(self, i):
        return self._connections[i].prints

    def _send(self, player_id, instruction, **kwargs):
        self._connections[player_id].send_message({"type": instruction, **kwargs})
