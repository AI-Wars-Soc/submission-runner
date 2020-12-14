from shared.messages import Sender
import numpy as np

sender = Sender()

arrays = []
for i in range(1024):
    arrays.append(np.random.random((1024, 1024, 1024)))  # Generate 1GB

sender.send_result("done")
