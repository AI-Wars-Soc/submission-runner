from enum import Enum, unique
import json
from json import JSONDecodeError
import random
from typing import Tuple, List
import collections


@unique
class MessageType(Enum):
    RESULT = "RESULT"
    PRINT = "PRINT"
    PROCESS_KILLED = "PROCESS_KILLED"
    ERROR_INVALID_NEW_KEY = "ERROR_INVALID_NEW_KEY"
    NEW_KEY = "NEW_KEY"
    ERROR_INVALID_ATTACHED_KEY = "ERROR_INVALID_ATTACHED_KEY"
    ERROR_INVALID_MESSAGE_TYPE = "ERROR_INVALID_MESSAGE_TYPE"


@unique
class DataType(Enum):
    STR = "STR"
    DICT = "DICT"
    INT = "INT"
    FLOAT = "FLOAT"


class MessageParseError(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        RuntimeError.__init__(self, reason)


class MessageInvalidTypeError(RuntimeError):
    def __init__(self, type_name: str):
        self.type_name = type_name
        RuntimeError.__init__(self, "Invalid type name: " + str(self.type_name))


class Message:
    def __init__(self, message_type: MessageType, data):
        self.message_type = message_type
        self.data = data

    def to_string(self, key: dict) -> str:
        message = {
            "message_type": str(self.message_type.value),
            "key": key,
            "data": self.data
        }
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

        if message_type not in [mt.value for mt in MessageType]:
            raise MessageInvalidTypeError(message_type)

        return key, Message(MessageType(message_type), data)

    @staticmethod
    def new_result(data) -> "Message":
        return Message(MessageType.RESULT, data)


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
    def __init__(self, lines: List[str]):
        self.messages = Receiver._process(lines)

    @staticmethod
    def _process(lines: List[str]) -> List["Message"]:
        key = None

        messages = []
        for line in lines:
            line = str(line).strip()
            if line.isspace() or line == "":
                continue

            message = Receiver._process_line(key, line)

            # Update key if message told us to
            if message.message_type == MessageType.NEW_KEY:
                key = message.data

            messages.append(message)
        return messages

    keyword_messages = {"Killed": Message(MessageType.PROCESS_KILLED, None)}

    @staticmethod
    def _process_line(key: dict, line: str) -> "Message":
        # Check for special messages
        if line in Receiver.keyword_messages:
            return Receiver.keyword_messages[line]

        # Check for commands
        try:
            received_key, message = Message.from_string(line)
        except MessageInvalidTypeError as e:
            return Message(MessageType.ERROR_INVALID_MESSAGE_TYPE, e.type_name)
        except MessageParseError:
            # No match => assume print statement
            return Message(MessageType.PRINT, line)

        # New key is a special case
        if message.message_type == MessageType.NEW_KEY:
            if key is not None:
                return Message(MessageType.ERROR_INVALID_NEW_KEY, received_key)
            return Message(MessageType.NEW_KEY, received_key)

        # If it's not a new key then it should have the current key
        if received_key != key:
            return Message(MessageType.ERROR_INVALID_ATTACHED_KEY, received_key)

        return message

