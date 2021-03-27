import re

import cuwais.database
import flask
from flask import request, Response
import os
import json

from shared.gamemodes import Gamemode
from shared.messages import MessageType, Message
from runner import sandbox
import logging

app = flask.Flask(__name__)
app.config["DEBUG"] = os.getenv('DEBUG') == 'True'

logging.basicConfig(level=logging.DEBUG if os.getenv('DEBUG') else logging.WARNING)


@app.route('/run', methods=['GET'])
def run():
    gamemode_name = str(request.args.get("gamemode", "info"))
    gamemode = Gamemode.get(gamemode_name)

    submissions_str = request.args.get("submissions", "").lower()
    submissions = [] if submissions_str is None or submissions_str == "" else submissions_str.split(",")

    if len(submissions) != gamemode.players:
        return Response(str({"error": f"Expected {gamemode.players} submissions, got {len(submissions)}"}),
                        status=400, mimetype='application/json')

    options = dict(request.args)
    for v in ["gamemode", "submissions"]:
        if v in options:
            del options[v]

    messages = sandbox.run_in_sandbox(gamemode, submissions, options)

    return Response(json.dumps(list(messages)), status=200, mimetype='application/json')


if __name__ == "__main__":
    cuwais.database.create_tables()
    if app.config["DEBUG"]:
        app.run(host="0.0.0.0", port=8080)
    else:
        from waitress import serve
        serve(app, host="0.0.0.0", port=8080)
