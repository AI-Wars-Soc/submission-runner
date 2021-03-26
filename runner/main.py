import re

import cuwais.database
import flask
from flask import request, Response
import os
import json
from shared.messages import MessageType, Message
from runner import sandbox
import logging

app = flask.Flask(__name__)
app.config["DEBUG"] = os.getenv('DEBUG') == 'True'

logging.basicConfig(level=logging.DEBUG if os.getenv('DEBUG') else logging.WARNING)


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
        return Response(str({"error": "Filter is not a valid csv"}), status=400, mimetype='application/json')

    types = set()
    for t in types_str.split(","):
        t = t.upper()
        if t in {"ANY", "ALL"}:
            types = set(MessageType)
        elif MessageType.is_message_type(t):
            types.add(MessageType(t))

    submissions_str = request.args.get("submissions", "")
    submissions_rex = re.compile("^[a-zA-Z0-9,]*$")
    if submissions_rex.match(submissions_str) is None:
        return Response(str({"error": "Submissions is not a valid csv"}), status=400, mimetype='application/json')
    submissions = submissions_str.split(",")

    messages = sandbox.run_in_sandbox(file, submissions)
    results = list(Message.filter(messages, types))

    return Response(json.dumps(results), status=200, mimetype='application/json')


if __name__ == "__main__":
    cuwais.database.create_tables()
    if app.config["DEBUG"]:
        app.run(host="0.0.0.0", port=8080)
    else:
        from waitress import serve
        serve(app, host="0.0.0.0", port=8080)
