from shared.message_connection import Sender
import time

sender = Sender()

time.sleep(1000000)

sender.send_result("done")
