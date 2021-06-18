import abc
import builtins
import itertools
import time
from enum import Enum, unique
import json
from json import JSONDecodeError
import random
from typing import Iterator, Callable, Optional, Any

import chess

from runner.logger import logger
from shared.exceptions import MissingFunctionError, ExceptionTraceback, FailsafeError


class ConnectionNotActiveError(RuntimeError):
    def __init__(self):
        super(ConnectionNotActiveError, self).__init__()


class ConnectionTimedOutError(RuntimeError):
    def __init__(self, container):
        self.container = container
        super().__init__()


@unique
class MessageType(Enum):
    NEW_KEY = "NEW_KEY"
    RESULT = "RESULT"
    PRINT = "PRINT"
    END = "END"

    @staticmethod
    def is_message_type(val: str):
        return val in [mt.value for mt in MessageType]


class MessageParseError(RuntimeError):
    pass


class MessageParseJSONError(MessageParseError):
    pass


class MessageParseTypeError(MessageParseError):
    pass


class MessageInvalidTypeError(MessageParseError):
    def __init__(self, type_name: str):
        self.type_name = type_name
        super().__init__(self, "Invalid type name: " + str(self.type_name))


class MessageInvalidNewKey(MessageParseError):
    def __init__(self, new_key: int):
        self.new_key = new_key
        super().__init__(self, "Invalid new key: " + hex(self.new_key))


class MessageInvalidAttachedKey(MessageParseError):
    def __init__(self, key: int):
        self.key = key
        super().__init__(self, "Invalid new key: " + hex(self.key))


class Message:
    def __init__(self, key: Optional[int], message_type: MessageType, data):
        self.key = key
        self.message_type = MessageType(message_type)
        self.data = data

    def is_end(self):
        return self.message_type == MessageType.END

    def __str__(self):
        return "<Message type: {}; data: {:20s}>".format(str(self.message_type.value), str(self.data))

    @staticmethod
    def new_result(key: int, data) -> "Message":
        return Message(key, MessageType.RESULT, data)


_input = builtins.input


def _input_receiver(input_function=None) -> Iterator[str]:
    if input_function is None:
        input_function = _input
    while True:
        s = input_function()
        yield s


class HandshakeFailedError(RuntimeError):
    def __init__(self, prints: Iterator[str]):
        self.prints = prints
        super().__init__()


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
    def complete(self):
        pass

    @abc.abstractmethod
    def call(self, method_name, *args, **kwargs) -> Any:
        """Calls a function with name method_name and args and kwargs as given.
        Raises ConnectionNotActiveError if the container is no longer active,
        or raises ConnectionTimedOutError if the container times out while we are waiting"""
        pass

    @abc.abstractmethod
    def ping(self) -> float:
        """Records the time taken for a message to be sent, parsed and responded to.
        Raises ConnectionNotActiveError if the container is no longer active,
        or raises ConnectionTimedOutError if the container times out while we are waiting"""
        pass


class MessagePrintConnection(Connection):
    _in_stream: Iterator[Message]

    def __init__(self, out_handler: Callable[[str], Any] = None, in_stream: Iterator[str] = None):
        # Set up output
        self._out_handler = out_handler if out_handler is not None else lambda x: print(x, flush=True)
        self._out_key = random.randint(-0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF)
        self._handshake_out()

        # Connect input
        in_stream_text = in_stream if in_stream is not None else _input_receiver()
        self._in_stream = MessagePrintConnection._make_messages_iterator(in_stream_text)
        self._in_key = None
        self._handshake_in()

        self._done = False
        self._prints = []

    def get_prints(self) -> str:
        return "\n".join(self._prints)

    def get_next_message_data(self):
        if self._done:
            raise ConnectionNotActiveError()

        for message in self._in_stream:
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
        self.send_message(Message(self._out_key, MessageType.END, {}))
        messages = []
        while True:
            try:
                data = self.get_next_message_data()
                messages.append(data)
            except (ConnectionNotActiveError, ConnectionTimedOutError):
                break
        return messages

    def call(self, method_name, *args, **kwargs) -> Any:
        self._send("call", method_name=method_name, method_args=args, method_kwargs=kwargs)

        return self.get_next_message_data()

    def ping(self) -> float:
        start_time = time.time_ns()
        self._send("ping")

        self.get_next_message_data()
        end_time = time.time_ns()

        delta = (end_time - start_time) / 1e9

        logger.debug(f"Ping delta: {delta}")

        return delta

    def _handshake_out(self):
        message = Message(None, MessageType.NEW_KEY, self._out_key)
        self.send_message(message)

    def _handshake_in(self):
        prints = []
        for message in self._in_stream:
            if message.message_type == MessageType.NEW_KEY:
                self._in_stream = itertools.chain(prints, self._in_stream)
                return
            if message.message_type == MessageType.PRINT:
                prints.append(message)

        raise HandshakeFailedError([p.data for p in prints])

    @staticmethod
    def _make_messages_iterator(lines: Iterator[str]) -> Iterator[Message]:
        key = None

        for line in lines:
            line = str(line).strip()
            if line.isspace() or line == "":
                continue

            message = MessagePrintConnection._process_line(key, line)

            # Update key if message told us to
            if message.message_type == MessageType.NEW_KEY:
                key = message.data

            if message.message_type == MessageType.END:
                yield message
                return

            yield message

    @staticmethod
    def _message_from_string(s: str) -> "Message":
        try:
            message = json.loads(s, cls=Decoder)
        except JSONDecodeError:
            raise MessageParseJSONError("Invalid json object: " + s)

        if not isinstance(message, Message):
            raise MessageParseTypeError("Invalid message type (is {}): {}".format(str(type(message)), s))

        return message

    @staticmethod
    def _process_line(key: int, line: str) -> "Message":
        # Check for commands
        try:
            message = MessagePrintConnection._message_from_string(line)
        except MessageParseError:
            # No match => assume print statement
            return Message(key, MessageType.PRINT, line)

        # New key is a special case
        if message.message_type == MessageType.NEW_KEY:
            if key is not None:
                raise MessageInvalidNewKey(key)
            return message

        # If it's not a new key then it should have the current key
        if message.key is None or message.key != key:
            raise MessageInvalidAttachedKey(key)

        return message

    def _send(self, instruction, **kwargs):
        self.send_result({"type": instruction, **kwargs})

    def send_result(self, data):
        message = Message(self._out_key, MessageType.RESULT, data)
        self.send_message(message)

    def send_message(self, message):
        if self._done:
            raise ConnectionNotActiveError()

        s = json.dumps(message, cls=Encoder)
        self._out_handler(s)


class Encoder(json.JSONEncoder):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._encoders = {Message: Encoder._message,
                          MissingFunctionError: Encoder._missing_function_error,
                          FailsafeError: Encoder._failsafe_error,
                          ExceptionTraceback: Encoder._exception_trace,
                          chess.Board: Encoder._chessboard,
                          chess.Move: Encoder._chess_move}

    @staticmethod
    def _message(message: Message):
        return {'__custom_type': 'message',
                'key': message.key,
                'type': str(message.message_type.value),
                'data': message.data}

    @staticmethod
    def _missing_function_error(e: MissingFunctionError):
        return {'__custom_type': 'missing_function_error',
                'str': str(e)}

    @staticmethod
    def _failsafe_error(e: FailsafeError):
        return {'__custom_type': 'failsafe_error',
                'str': str(e)}

    @staticmethod
    def _exception_trace(e: ExceptionTraceback):
        return {'__custom_type': 'exception_trace',
                'msg': str(e.e_trace)}

    @staticmethod
    def _chessboard(board: chess.Board):
        return {'__custom_type': 'chessboard',
                'fen': board.fen(),
                'chess960': board.chess960}

    @staticmethod
    def _chess_move(move: chess.Move):
        return {'__custom_type': 'chess_move',
                'uci': move.uci()}

    def default(self, obj):
        if type(obj) in self._encoders:
            return self._encoders[type(obj)](obj)
        return super(Encoder, self).default(obj)


class Decoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)
        self._decoders = {'message': Decoder._message,
                          'missing_function_error': Decoder._missing_function_error,
                          'failsafe_error': Decoder._failsafe_error,
                          'exception_trace': Decoder._exception_trace,
                          'chessboard': Decoder._chessboard,
                          'chess_move': Decoder._chess_move}

    @staticmethod
    def _message(data: dict):
        return Message(key=data['key'], message_type=MessageType(data['type']), data=data['data'])

    @staticmethod
    def _missing_function_error(e: dict):
        return MissingFunctionError(e['str'])

    @staticmethod
    def _failsafe_error(e: dict):
        return FailsafeError(e['str'])

    @staticmethod
    def _exception_trace(e: dict):
        return ExceptionTraceback(e['msg'])

    @staticmethod
    def _message_type(message_type: str):
        return MessageType(message_type)

    @staticmethod
    def _chessboard(data: dict):
        return chess.Board(fen=data['fen'], chess960=data['chess960'])

    @staticmethod
    def _chess_move(data: dict):
        return chess.Move.from_uci(data['uci'])

    def object_hook(self, obj):
        if '__custom_type' not in obj:
            return obj
        custom_type = obj['__custom_type']
        if custom_type in self._decoders:
            return self._decoders[custom_type](obj)

        return obj
