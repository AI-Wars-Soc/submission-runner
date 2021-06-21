from shared.message_connection import Sender

sender = Sender()
with open("./sandbox/tests/new_data.txt", 'w') as f:
    f.write("Hello Again World!")
with open("./sandbox/tests/new_data.txt", 'r') as f:
    sender.send_result(f.readlines())
