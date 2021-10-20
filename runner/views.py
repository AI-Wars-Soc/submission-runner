import json
import logging
import traceback

from cuwais.gamemodes import Gamemode
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi_utils.timing import add_timing_middleware
from starlette.responses import Response

from runner import gamemode_runner
from runner.logger import logger
from runner.web_connection import websocket_game
from shared.message_connection import Encoder

from config import DEBUG, PROFILE

app = FastAPI(root_path="/")
if DEBUG and PROFILE:
    add_timing_middleware(app, record=logging.info, prefix="app", exclude="untimed")


@app.get('/run')
async def run_endpoint(submissions: str, options: str = None, gamemode: str = "chess", moves: int = 2 << 32):
    try:
        submissions = json.loads(submissions)
        options = json.loads(options)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422,
                            detail=f"Invalid json string")

    if not isinstance(submissions, list) or not all(isinstance(i, str) for i in submissions):
        raise HTTPException(status_code=422,
                            detail=f"Submissions is not a list of strings: {submissions}")

    gamemode = Gamemode.get(gamemode)

    if len(submissions) != gamemode.player_count:
        raise HTTPException(status_code=422,
                            detail=f"Expected {gamemode.player_count} submissions, got {len(submissions)}")

    if options is None:
        options = {}

    try:
        parsed = await gamemode_runner.run(gamemode, submissions, options, moves)
    except:
        logger.error(traceback.format_exc())
        raise

    return Response(content=json.dumps(parsed, cls=Encoder), media_type="application/json")


@app.websocket("/ws/run")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await websocket_game(websocket)
    except:
        logger.error(traceback.format_exc())
        raise
