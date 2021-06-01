import builtins

from shared.messages import Sender, Receiver, input_receiver


def main():
    sender = Sender()
    receiver = Receiver(input_receiver())
    in_stream = receiver.messages_iterator

    # Reduce things that can accidentally go wrong
    def fake_input(*args, **kwargs):
        return ""
    builtins.input = fake_input

    sender.send_result(input())
    sender.send_result(next(in_stream))


if __name__ == "__main__":
    main()
