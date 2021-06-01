import builtins

from sandbox import player_import
from shared.messages import Sender, Receiver, input_receiver, MessageType


def call(method_name, method_args, method_kwargs):
    fun = player_import.get_player_function("ai", method_name)
    result = fun(*method_args, **method_kwargs)
    return ""if result is None else result


def main():
    sender = Sender()
    receiver = Receiver(input_receiver())
    in_stream = receiver.messages_iterator

    # Reduce things that can accidentally go wrong
    def fake_input(*args, **kwargs):
        return ""
    builtins.input = fake_input

    while True:
        # Get next instruction from host
        instruction = None
        for message in in_stream:
            if message.is_end():
                return
            if message.message_type != MessageType.RESULT:
                continue
            instruction = message.data
            break

        if instruction is None:
            return

        # Decode
        t = instruction["type"]
        del instruction["type"]
        dispatch = {"call": call}[t]

        # Execute
        data = dispatch(**instruction)
        if data is not None:
            sender.send_result(data)


if __name__ == "__main__":
    main()
