import flask
import os
import json
import sandbox

# Test that docker is working before starting the server
print(sandbox.run_folder_in_sandbox("./runner/test"))

app = flask.Flask(__name__)
app.config["DEBUG"] = os.getenv('SANDBOX_API_DEBUG')


@app.route('/', methods=['GET'])
def home():
    return json.dumps(sandbox.run_folder_in_sandbox("./runner/test"))


app.run(host='0.0.0.0')
