import builtins
import sys
import traceback

from sandbox import player_import, info
from shared.exceptions import MissingFunctionError, ExceptionTraceback
from shared.messages import MessageType, Connection


def call(method_name, method_args, method_kwargs):
    fun = player_import.get_player_function("ai", method_name)
    result = fun(*method_args, **method_kwargs)
    return "" if result is None else result


def ping():
    return "pong"


def get_info():
    return info.get_info()


def get_instructions(messages):
    for message in messages:
        if message.is_end():
            break
        elif message.message_type != MessageType.RESULT:
            continue
        else:
            yield message.data


def main():
    connection = Connection()
    in_stream = connection.receive
    instructions = get_instructions(in_stream)

    # Reduce things that can accidentally go wrong
    def fake_input(*args, **kwargs):
        return ""
    builtins.input = fake_input

    # Fetch
    for instruction in instructions:
        try:
            # Decode
            t = instruction["type"]
            del instruction["type"]
            dispatch = {"call": call,
                        "ping": ping,
                        "info": get_info}[t]

            # Execute
            data = dispatch(**instruction)

            # Sendback
            connection.send_result(data)
        except MissingFunctionError as e:
            connection.send_result(e)
        except Exception:
            traceback.print_exc()
            tb = traceback.format_exception(*sys.exc_info())

            connection.send_result(ExceptionTraceback(tb))


if __name__ == "__main__":
    main()
