from shared.messages import Sender

sender = Sender()
with open("/sandbox-scripts/tests/new_data.txt", 'w') as f:
    f.write("Hello Again World!")
with open("/sandbox-scripts/tests/new_data.txt", 'r') as f:
    sender.send_result(f.readlines())
