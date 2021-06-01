import builtins
import itertools
import re
from enum import Enum, unique
import json
from json import JSONDecodeError
import random
from typing import Tuple, Iterator, Set, Union, Callable, Optional, Any
import collections


@unique
class MessageType(Enum):
    NEW_KEY = "NEW_KEY"
    RESULT = "RESULT"
    PRINT = "PRINT"
    END = "END"
    ERROR_PROCESS_KILLED = "ERROR_PROCESS_KILLED"
    ERROR_PROCESS_TIMEOUT = "ERROR_PROCESS_TIMEOUT"
    ERROR_INVALID_NEW_KEY = "ERROR_INVALID_NEW_KEY"
    ERROR_INVALID_ATTACHED_KEY = "ERROR_INVALID_ATTACHED_KEY"
    ERROR_INVALID_MESSAGE_TYPE = "ERROR_INVALID_MESSAGE_TYPE"
    ERROR_INVALID_SUBMISSION = "ERROR_INVALID_SUBMISSION"

    @staticmethod
    def is_message_type(val: str):
        return val in [mt.value for mt in MessageType]


class MessageParseError(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        RuntimeError.__init__(self, reason)


class MessageInvalidTypeError(RuntimeError):
    def __init__(self, type_name: str):
        self.type_name = type_name
        RuntimeError.__init__(self, "Invalid type name: " + str(self.type_name))


class Message(dict):
    def __init__(self, message_type: MessageType, data: Optional[Union[list, dict, int, float, bool]]):
        self.message_type = message_type
        self.data = data

        message = {
            "message_type": str(self.message_type.value),
            "data": self.data
        }
        dict.__init__(self, message)

    ERROR_TYPES = {MessageType.ERROR_PROCESS_KILLED,
                   MessageType.ERROR_PROCESS_TIMEOUT,
                   MessageType.ERROR_INVALID_NEW_KEY,
                   MessageType.ERROR_INVALID_ATTACHED_KEY,
                   MessageType.ERROR_INVALID_MESSAGE_TYPE,
                   MessageType.ERROR_INVALID_SUBMISSION}

    END_TYPES = {MessageType.END,
                 *ERROR_TYPES}

    def is_error(self):
        return self.message_type in self.ERROR_TYPES

    def is_end(self):
        return self.message_type in self.END_TYPES

    def to_string(self, key: dict) -> str:
        message = dict(self)
        message["key"] = key
        return json.dumps(message)

    def __str__(self):
        return "<Message type: {}; data: {:20s}>".format(str(self.message_type.value), str(self.data))

    @staticmethod
    def from_string(s: str) -> Tuple[dict, "Message"]:
        try:
            message = json.loads(s)
        except JSONDecodeError:
            raise MessageParseError("Invalid json object: " + s)

        if not isinstance(message, collections.Mapping):
            raise MessageParseError("Invalid message type (is {}): {}".format(str(type(message)), s))

        try:
            message_type = message["message_type"]
            key = message["key"]
            data = message["data"]
        except KeyError:
            raise MessageParseError("Invalid message dict: " + str(message))

        if not MessageType.is_message_type(message_type):
            raise MessageInvalidTypeError(message_type)

        return key, Message(MessageType(message_type), data)

    @staticmethod
    def new_result(data) -> "Message":
        return Message(MessageType.RESULT, data)

    @staticmethod
    def filter(messages: Iterator["Message"], types: Union[Set[MessageType], MessageType]) -> Iterator["Message"]:
        if isinstance(types, MessageType):
            types = {types}

        return filter(lambda m: m.message_type in types, messages)

    @staticmethod
    def get_datas(messages: Iterator["Message"]) -> Iterator:
        return map(lambda m: m.data, messages)


class MessageInputStream:
    def __init__(self):
        self._receivers = []

    def register_receiver(self, f: Callable[[Message], Any]):
        self._receivers.append(f)

    def send(self, m: Message):
        for f in self._receivers:
            f(m)


class Sender:
    def __init__(self, handler: Callable[[str], None] = lambda x: print(x, flush=True)):
        self._handler = handler
        self._key = {"code": hex(random.randint(-0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF))}

        # Send a new key message
        message = Message(MessageType.NEW_KEY, self._key)
        self.send(message)

    def send(self, message: Message):
        self._handler(message.to_string(self._key))

    def send_result(self, data):
        self.send(Message.new_result(data))


def input_receiver(input_function=builtins.input) -> Iterator[str]:
    while True:
        s = input_function()
        if s is None or s == "":
            return
        yield s


class Receiver:
    def __init__(self, lines: Iterator[str]):
        self._lines = lines
        self._iterator = Receiver._filter_middle_ends_to_prints(Receiver._handshake(self._make_messages_iterator()))

    @staticmethod
    def _handshake(iterator: Iterator[Message]) -> Iterator[Message]:
        before = []
        for m in iterator:
            if m.message_type == MessageType.NEW_KEY:
                break
            before.append(m)

        return itertools.chain(before, iterator)

    @property
    def messages_iterator(self) -> Iterator[Message]:
        return self._iterator

    def _make_messages_iterator(self) -> Iterator[Message]:
        key = None

        for line in self._lines:
            line = str(line).strip()
            if line.isspace() or line == "":
                continue

            message = Receiver._process_line(key, line)

            # Update key if message told us to
            if message.message_type == MessageType.NEW_KEY:
                key = message.data

            yield message

    @staticmethod
    def _filter_middle_ends_to_prints(messages: Iterator["Message"]) -> Iterator["Message"]:
        """Takes a message stream and converts all of the messages that should be at the end
        of a set of messages but that occur in the middle into print statements with their originally
        printed values. This fixes the edge case that someone prints one of the used keywords
        (e.g. 'Done') inside their code."""
        ends = []

        for message in messages:
            if message.is_end():
                ends.append(message)
                continue

            for end in ends:
                yield Message(MessageType.PRINT, data=end.data)
            ends = []

            yield message

        yield from ends

    keyword_messages = {".+\\d+ Killed\\s+timeout .+ python3 .+": MessageType.ERROR_PROCESS_KILLED,
                        "Done": MessageType.END,
                        "Timeout": MessageType.ERROR_PROCESS_TIMEOUT}

    @staticmethod
    def _process_line(key: dict, line: str) -> "Message":
        # Check for special messages
        for keyword in Receiver.keyword_messages.keys():
            keyword_rex = re.compile("^{}$".format(keyword))
            if keyword_rex.match(line) is not None:
                return Message(Receiver.keyword_messages[keyword], {"str": line})

        # Check for commands
        try:
            received_key, message = Message.from_string(line)
        except MessageInvalidTypeError as e:
            return Message(MessageType.ERROR_INVALID_MESSAGE_TYPE, {"given": e.type_name})
        except MessageParseError:
            # No match => assume print statement
            return Message(MessageType.PRINT, {"str": line})

        # New key is a special case
        if message.message_type == MessageType.NEW_KEY:
            if key is not None:
                return Message(MessageType.ERROR_INVALID_NEW_KEY, received_key)
            return Message(MessageType.NEW_KEY, received_key)

        # If it's not a new key then it should have the current key
        if received_key is None or received_key != key:
            return Message(MessageType.ERROR_INVALID_ATTACHED_KEY, received_key)

        return message
