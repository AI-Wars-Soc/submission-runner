import json

import flask
from cuwais.config import config_file
from flask import request, Response, abort
from werkzeug.middleware.profiler import ProfilerMiddleware

from runner import gamemodes
from shared.message_connection import Encoder

app = flask.Flask(__name__)
app.config["DEBUG"] = config_file.get("debug")

if app.config["DEBUG"]:
    app.config['PROFILE'] = config_file.get("profile")
    app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[30])

with open("/run/secrets/secret_key") as secrets_file:
    secret = "".join(secrets_file.readlines())
    app.secret_key = secret
    app.config["SECRET_KEY"] = secret


@app.route('/run', methods=['GET'])
def run_endpoint():
    gamemode_name = str(request.args.get("gamemode", "chess"))
    gamemode = gamemodes.Gamemode.get(gamemode_name)

    if gamemode is None:
        abort(404)

    submissions_str = request.args.get("submissions", "").lower()
    submissions = [] if submissions_str is None or submissions_str == "" else submissions_str.split(",")

    if len(submissions) != gamemode.player_count:
        return Response(str({"error": f"Expected {gamemode.player_count} submissions, got {len(submissions)}"}),
                        status=400, mimetype='application/json')

    moves = int(request.args.get("moves", 2 << 32))

    options = dict(request.args)
    for v in ["gamemode", "submissions", "moves"]:
        if v in options:
            del options[v]

    parsed = gamemode.run(submissions, options, moves)

    return Response(json.dumps(parsed, cls=Encoder), status=200, mimetype='application/json')
