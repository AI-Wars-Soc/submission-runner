import builtins
import os
import sys
import traceback

from sandbox import player_import, info
from shared.exceptions import MissingFunctionError, ExceptionTraceback, FailsafeError
from shared.message_connection import MessagePrintConnection
from shared.connection import ConnectionTimedOutError, ConnectionNotActiveError


def failsafes():
    # Check nothing is writable
    for path in info.get_all_writable():
        is_dir = os.path.isdir(path)
        if is_dir:
            path = os.path.join(path, "test.txt")
        if not is_dir:
            if path.startswith("/dev") or path.startswith("/proc"):
                continue
        if info.write_until_full(path, remove=is_dir) == "No Limit":
            raise FailsafeError(f"Writable {'directory' if is_dir else 'file'}: " + path)


def call(method_name, method_args, method_kwargs):
    fun = player_import.get_player_function("ai", method_name)
    result = fun(*method_args, **method_kwargs)
    return "" if result is None else result


def ping():
    return "pong"


def get_info():
    return info.get_info()


def get_instructions(connection):
    while True:
        try:
            yield connection.get_next_message_data()
        except (ConnectionTimedOutError, ConnectionNotActiveError):
            return


def main():
    connection = MessagePrintConnection()
    instructions = get_instructions(connection)

    # Check that we haven't got any security holes
    if os.getenv("DEBUG").lower().startswith("t"):
        failsafes()

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
