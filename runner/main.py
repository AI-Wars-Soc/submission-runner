import json
import logging

import cuwais.database
import flask
from cuwais.config import config_file
from flask import request, Response

from runner import gamemodes
from runner.matchmaker import Matchmaker
from shared.messages import Encoder

app = flask.Flask(__name__)
app.config["DEBUG"] = config_file.get("debug")

logging.basicConfig(level=logging.DEBUG if app.config["DEBUG"] else logging.WARNING)


@app.route('/run', methods=['GET'])
def run():
    gamemode_name = str(request.args.get("gamemode", "info"))
    gamemode = gamemodes.Gamemode.get(gamemode_name)

    submissions_str = request.args.get("submissions", "").lower()
    submissions = [] if submissions_str is None or submissions_str == "" else submissions_str.split(",")

    if len(submissions) != gamemode.players:
        return Response(str({"error": f"Expected {gamemode.players} submissions, got {len(submissions)}"}),
                        status=400, mimetype='application/json')

    options = dict(request.args)
    for v in ["gamemode", "submissions"]:
        if v in options:
            del options[v]

    parsed = gamemode.run(submissions, options)

    return Response(json.dumps(parsed, cls=Encoder), status=200, mimetype='application/json')


def main():
    # Get some options
    gamemode = gamemodes.Gamemode.get(config_file.get("gamemode.id").lower())
    options = config_file.get("gamemode.options")
    matchmakers = int(config_file.get("submission_runner.matchmakers"))
    seconds_per_run = int(config_file.get("submission_runner.target_seconds_per_game"))

    # Set up database
    cuwais.database.create_tables()

    # Start up matchmakers
    for i in range(matchmakers):
        matchmaker = Matchmaker(gamemode, options, i == 0, seconds_per_run)
        matchmaker.start()

    # Serve webpages
    if app.config["DEBUG"]:
        app.run(host="0.0.0.0", port=8080)
    else:
        from waitress import serve
        serve(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
