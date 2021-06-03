import builtins
import traceback

from sandbox import player_import
from shared.messages import Sender, Receiver, input_receiver, MessageType


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
    sender = Sender()
    receiver = Receiver(input_receiver())
    in_stream = receiver.messages_iterator
    instructions = get_instructions(in_stream)
    print("")  # TODO: Remove. This does something for some reason, probably flushes some stream somewhere but it's required

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
            sender.send_result(None)
            return

        # Sendback
        sender.send_result(data)
        print("Finished fetch", flush=True)


if __name__ == "__main__":
    main()
