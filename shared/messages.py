import re
from enum import Enum, unique
import json
from json import JSONDecodeError
import random
from typing import Tuple, Iterator, Set, Union
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
    ERROR_INVALID_ENTRY_FILE = "ERROR_INVALID_ENTRY_FILE"

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
    def __init__(self, message_type: MessageType, data: dict):
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
                   MessageType.ERROR_INVALID_ENTRY_FILE}

    END_TYPES = {MessageType.END,
                 MessageType.ERROR_INVALID_ENTRY_FILE,
                 MessageType.ERROR_PROCESS_TIMEOUT,
                 MessageType.ERROR_PROCESS_KILLED}

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

    @staticmethod
    def filter_middle_ends_to_prints(messages: Iterator["Message"]) -> Iterator["Message"]:
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


class Sender:
    def __init__(self):
        self._key = {"code": hex(random.randint(-0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF))}

        # Send a new key message
        message = Message(MessageType.NEW_KEY, self._key)
        self.send(message)

    def send(self, message: Message):
        print(message.to_string(self._key), flush=True)

    def send_result(self, data):
        self.send(Message.new_result(data))


class Receiver:
    def __init__(self, lines: Iterator[str]):
        self._lines = lines

    def get_messages_iterator(self) -> Iterator[Message]:
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
        if received_key != key:
            return Message(MessageType.ERROR_INVALID_ATTACHED_KEY, received_key)

        return message

