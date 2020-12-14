from shared.messages import Sender

sender = Sender()
with open("/sandbox-scripts/tests/data.txt", 'w') as f:
    f.write("Goodbye World!")
with open("/sandbox-scripts/tests/data.txt", 'r') as f:
    sender.send_result(f.readlines())
