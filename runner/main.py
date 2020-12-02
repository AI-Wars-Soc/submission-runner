import flask
import os
import json
import sandbox

app = flask.Flask(__name__)
app.config["DEBUG"] = os.getenv('SANDBOX_API_DEBUG')


@app.route('/', methods=['GET'])
def home():
    return json.dumps(sandbox.run_folder_in_sandbox("test.py"))


app.run(host='0.0.0.0')
