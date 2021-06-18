import os
from shared.message_connection import Sender

sender = Sender()
with open("/tmp/big_data.txt", 'wb') as f:
    f.write(os.urandom(1*1024*1024))  # 1MB
with open("/tmp/big_data.txt", 'rb') as f:
    sender.send_result(len(f.read()))
