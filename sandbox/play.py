import builtins
import traceback

from sandbox import player_import
from shared.messages import MessageType, Connection


def call(method_name, method_args, method_kwargs):
    fun = player_import.get_player_function("ai", method_name)
    result = fun(*method_args, **method_kwargs)
    return "" if result is None else result


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
    print("Starting fetch", flush=True)
    for instruction in instructions:
        print(f"Instruction {instruction}", flush=True)
        # Decode
        t = instruction["type"]
        del instruction["type"]
        dispatch = {"call": call}[t]

        # Execute
        try:
            data = dispatch(**instruction)
        except:  # ignore
            traceback.print_exc()
            connection.send_result(None)
            return

        # Sendback
        connection.send_result(data)
        print("Finished fetch", flush=True)


if __name__ == "__main__":
    main()
