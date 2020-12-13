import re
import flask
from flask import request, Response
import os
import json
import sandbox
from shared.messages import MessageType, Message

app = flask.Flask(__name__)
app.config["DEBUG"] = os.getenv('SANDBOX_API_DEBUG')


@app.route('/run', methods=['GET'])
def home():
    file = str(request.args.get("file", "info"))
    if not file.isalpha():
        return Response(str({"error": "File contains invalid characters"}), status=400, mimetype='application/json')

    types_str = request.args.get("filter", "all")
    types_rex = re.compile("^[a-zA-Z_,]+$")
    if types_rex.match(types_str) is None:
        return Response(str({"error": "Filter is not valid csv"}), status=400, mimetype='application/json')

    types = set()
    for t in types_str.split(","):
        t = t.upper()
        if t == "ANY":
            types = set(MessageType)
        elif MessageType.is_message_type(t):
            types.add(MessageType(t))

    messages = sandbox.run_in_sandbox(file + ".py")
    results = list(Message.filter(messages, types))

    return Response(json.dumps(results), status=200, mimetype='application/json')


app.run(host='0.0.0.0')