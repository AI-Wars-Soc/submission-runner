from shared.message_connection import Sender

sender = Sender()
with open("./sandbox/tests/data.txt", 'w') as f:
    f.write("Goodbye World!")
with open("./sandbox/tests/data.txt", 'r') as f:
    sender.send_result(f.readlines())
