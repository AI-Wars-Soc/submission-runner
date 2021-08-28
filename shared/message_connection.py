import builtins
from enum import Enum, unique
import json
from json import JSONDecodeError
from typing import Iterator, Callable, Any, AsyncGenerator, Awaitable

import chess

from shared.connection import Connection, ConnectionNotActiveError
from shared.exceptions import MissingFunctionError, ExceptionTraceback, FailsafeError


@unique
class MessageType(Enum):
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


class Message:
    def __init__(self, message_type: MessageType, data):
        self.message_type = MessageType(message_type)
        self.data = data

    def is_end(self):
        return self.message_type == MessageType.END

    def __str__(self):
        return "<Message type: {}; data: {:20s}>".format(str(self.message_type.value), str(self.data))

    @staticmethod
    def new_result(data) -> "Message":
        return Message(MessageType.RESULT, data)


_input = builtins.input


async def _input_receiver(input_function=None) -> AsyncGenerator[str, None]:
    if input_function is None:
        input_function = _input
    while True:
        s = input_function()
        yield s


class HandshakeFailedError(RuntimeError):
    def __init__(self, prints: Iterator[str]):
        self.prints = prints
        super().__init__()


class MessagePrintConnection(Connection):
    _in_stream: AsyncGenerator[Message, None]

    def __init__(self, out_handler: Callable[[str], Any] = None, in_stream: AsyncGenerator[str, None] = None,
                 name: str = ""):
        # Set up state
        self._done = False
        self._prints = []
        self._name = name

        # Set up output
        self._out_handler = out_handler if out_handler is not None else lambda x: print(x, flush=True)

        # Connect input
        in_stream_text: AsyncGenerator[str, None] = in_stream if in_stream is not None else _input_receiver()
        self._in_stream = MessagePrintConnection._make_messages_iterator(in_stream_text)

    def get_prints(self) -> str:
        return "\n".join(self._prints)

    async def close(self):
        await self.send_message(Message(MessageType.END, {}))

    async def get_next_message_data(self):
        if self._done:
            raise ConnectionNotActiveError()

        async for message in self._in_stream:
            if message.message_type == MessageType.PRINT:
                self._prints.append(message.data)
            elif message.message_type == MessageType.RESULT:
                return message.data
            elif message.message_type == MessageType.END:
                self._done = True
                raise ConnectionNotActiveError()

        self._done = True
        return await self.get_next_message_data()  # Force an except

    async def send_call(self, method_name, method_args, method_kwargs):
        await self._send("call", method_name=method_name, method_args=method_args, method_kwargs=method_kwargs)

    async def send_ping(self):
        await self._send("ping")

    @staticmethod
    async def _make_messages_iterator(lines: AsyncGenerator[str, None]) -> AsyncGenerator[Message, None]:
        async for line in lines:
            line = str(line).strip()
            if line.isspace() or line == "":
                continue

            message = MessagePrintConnection._process_line(line)

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
    def _process_line(line: str) -> "Message":
        # Check for commands
        try:
            message = MessagePrintConnection._message_from_string(line)
        except MessageParseError:
            # No match => assume print statement
            return Message(MessageType.PRINT, line)

        return message

    async def _send(self, instruction, **kwargs):
        await self.send_result({"type": instruction, **kwargs})

    async def send_result(self, data):
        message = Message(MessageType.RESULT, data)
        await self.send_message(message)

    async def send_message(self, message: Message):
        if self._done:
            raise ConnectionNotActiveError()

        s = json.dumps(message, cls=Encoder)
        res = self._out_handler(s)
        if isinstance(res, Awaitable):
            await res

    def __str__(self):
        return f"MessagePrintConnection<{self._name}>"


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
        return Message(message_type=MessageType(data['type']), data=data['data'])

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
