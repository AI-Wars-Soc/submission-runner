import re
import flask
from flask import request, Response
import os
import json
from shared.messages import MessageType, Message
from runner import sandbox
import logging

app = flask.Flask(__name__)
app.config["DEBUG"] = os.getenv('SANDBOX_API_DEBUG')

logging.basicConfig(level=logging.DEBUG if os.getenv('SANDBOX_API_DEBUG') else logging.WARNING)


@app.route('/run', methods=['GET'])
def run():
    file = str(request.args.get("file", "info"))
    file_name_rex = re.compile("^[a-zA-Z0-9_/]+$")
    if file_name_rex.match(file) is None:
        return Response(str({"error": "File contains invalid characters"}), status=400, mimetype='application/json')
    file += ".py"

    types_str = request.args.get("filter", "any")
    types_rex = re.compile("^[a-zA-Z_,]+$")
    if types_rex.match(types_str) is None:
        return Response(str({"error": "Filter is not valid csv"}), status=400, mimetype='application/json')

    types = set()
    for t in types_str.split(","):
        t = t.upper()
        if t in {"ANY", "ALL"}:
            types = set(MessageType)
        elif MessageType.is_message_type(t):
            types.add(MessageType(t))

    messages = sandbox.run_in_sandbox(file)
    results = list(Message.filter(messages, types))

    return Response(json.dumps(results), status=200, mimetype='application/json')


app.run(host='0.0.0.0')
