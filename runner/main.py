import flask
import os
import json
import sandbox
import sandbox_recieve

app = flask.Flask(__name__)
app.config["DEBUG"] = os.getenv('SANDBOX_API_DEBUG')


@app.route('/', methods=['GET'])
def home():
    ran = sandbox.run_folder_in_sandbox("test.py")
    if ran["status"] == 200:
        ran["output"] = list(sandbox_recieve.Receiver(ran["output"]).received)
    return json.dumps(ran)


app.run(host='0.0.0.0')
