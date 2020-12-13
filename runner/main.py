import flask
import os
import json
import sandbox
from shared.messages import MessageType, Receiver

app = flask.Flask(__name__)
app.config["DEBUG"] = os.getenv('SANDBOX_API_DEBUG')


@app.route('/', methods=['GET'])
def home():
    ran = sandbox.run_folder_in_sandbox("test.py")
    if ran["status"] == 200:
        receiver = Receiver(ran["output"].split("\n"))
        messages = receiver.messages
        results = filter(lambda m: m.message_type == MessageType.RESULT, messages)
        prints = filter(lambda m: m.message_type == MessageType.PRINT, messages)

        for result in results:
            print(result.data, flush=True)

        ran["output"] = [m.data for m in prints]
    return json.dumps(ran)


app.run(host='0.0.0.0')
