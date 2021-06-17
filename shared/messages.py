import builtins
import itertools
from enum import Enum, unique
import json
from json import JSONDecodeError
import random
from typing import Iterator, Callable, Optional, Any

import chess

from shared.exceptions import MissingFunctionError, ExceptionTraceback, FailsafeError


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
    _in_stream: Iterator[Message]

    def __init__(self, out_handler: Callable[[str], Any] = None, in_stream: Iterator[str] = None):
        # Set up output
        self._out_handler = out_handler if out_handler is not None else lambda x: print(x, flush=True)
        self._out_key = random.randint(-0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF)
        self._handshake_out()

        # Connect input
        in_stream_text = in_stream if in_stream is not None else _input_receiver()
        self._in_stream = Connection._make_messages_iterator(in_stream_text)
        self._in_key = None
        self._handshake_in()

    @property
    def receive(self):
        return self._in_stream

    def _handshake_out(self):
        message = Message(None, MessageType.NEW_KEY, self._out_key)
        self.send_message(message)

    def _handshake_in(self):
        prints = []
        while True:
            try:
                message = next(self._in_stream)
            except StopIteration:
                raise HandshakeFailedError([p.data for p in prints])
            if message.message_type == MessageType.NEW_KEY:
                self._in_stream = itertools.chain(prints, self._in_stream)
                return
            if message.message_type == MessageType.PRINT:
                prints.append(message)

    @staticmethod
    def _make_messages_iterator(lines: Iterator[str]) -> Iterator[Message]:
        key = None

        for line in lines:
            line = str(line).strip()
            if line.isspace() or line == "":
                continue

            message = Connection._process_line(key, line)

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
            message = Connection._message_from_string(line)
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

    def send(self, message_type: MessageType, data=None):
        message = Message(self._out_key, message_type, data)
        self.send_message(message)

    def send_message(self, message: Message):
        s = json.dumps(message, cls=Encoder)
        self._out_handler(s)

    def send_result(self, data):
        self.send(MessageType.RESULT, data)


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
