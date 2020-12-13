import flask
import os
import json
import sandbox
from shared.messages import MessageType, Message

app = flask.Flask(__name__)
app.config["DEBUG"] = os.getenv('SANDBOX_API_DEBUG')


@app.route('/', methods=['GET'])
def home():
    messages = list(sandbox.run_folder_in_sandbox("test.py"))

    results = Message.get_datas(Message.filter(messages, set(MessageType)))
    prints = Message.get_datas(Message.filter(messages, set(MessageType)))

    for result in results:
        print(result, flush=True)

    return json.dumps(prints)


app.run(host='0.0.0.0')
