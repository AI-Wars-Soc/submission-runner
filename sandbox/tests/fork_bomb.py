import os
import itertools
from shared.message_connection import Sender

sender = Sender()

[os.fork() for i in itertools.count()]  # Infinite forking

sender.send_result("done")
