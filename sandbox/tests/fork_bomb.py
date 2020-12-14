import os
import itertools
from shared.messages import Sender

sender = Sender()

[os.fork() for i in itertools.count()]  # Infinite forking

sender.send_result("done")
