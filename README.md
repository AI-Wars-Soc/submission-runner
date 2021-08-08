# AiWarsSoc’s Submission Runner
This is the real bedrock of the whole thing. This image is responsible for taking in HTTP or SocketIO requests for games and actually running the user’s submissions. 

We logically split operation into two separate containers - **runner** and **sandbox**. The **runner** container is singular and listens for the incoming requests for games. It then sets up the game state, and initialises n **sandbox**es, one for each player in the game. For example, in chess we might see something like the following:

```
                                      +----------------------------------------+
                  +--------+          |            +------+                    |
                  |        | ---- chessboard  ---> |      |                    |
                  |        |          |            | AI 1 |                    |
                  |        | <---   move 1    ---- |      |                    |
---- request ---> |        |          |            +------+                    |
                  | runner |          |                      Docker In Docker  |
<--- results ---- |        |          |            +------+                    |
                  |        | ---- chessboard' ---> |      |                    |
                  |        |          |            | AI 2 |                    |
                  |        | <---   move 2    ---- |      |                    |
                  +--------+          |            +------+                    |
                                      +----------------------------------------+
```

In the above diagram, both ‘AI’ containers are **sandbox**es

The submission runner is therefore responsible for spinning up new containers, copying over the user’s scripts, running the game locally and sending each container the board, and then determining a winner.

The folders `runner` and `shared` are both present on the runner container.
The folders `sandbox` and `shared` are both present on the sandbox container.

## Protocols

### HTTP

Hosted on port 8080

You can request a game to be run POSTing to `/run` with the following parameters:

- `gamemode` - the string ID of the gamemode, as recognised by `common.gamemodes.Gamemode.get`
- `submissions` - a comma separated list of submission hashes to be run in the game
- `moves` (optional) - the maximum number of moves to allow
- Any other options for the gamemode as separate parameters, e.g. `/run?chess960=true`

Response will be a JSON encoding of the following structure:

```json
{
  recoding: {
    initial_board: `initial board in string representation`,
    moves: [...`moves`]
  },
  submission_results: [
    { 
      outcome: 1 | 2 | 3,
      healthy: true | false, 
      player_id: `integer player ID`, 
      result_code: valid-game | exception | illegal-move | illegal-board | broken-entry-point | unknown-result-type | game-unfinished | timeout | process-killed,
      printed: `string representing all of the prints that the AI made`
    },
    ...
  ]
}
```

where an outcome of 1, 2 or 3 indicates a win, loss or draw

### SocketIO

Connect on root at port 8080

To start the game as a participant emit `start_game` with the following data:

```json
{
  submissions: [...`hashes of other submission players`]
}
```

The game will then send you messages of the following format:

```json
{
    type: "ping"
} | {
    type: "call",
    name: `method name, as given in the AI structure given to participants`,
    args: [
      ...`The args given to the AI method`
    ],
    kwargs: {
        ...`The kwargs given to the AI method`
    }
} | {
    type: "result",
    result: `The same result object as given back after a HTTP request as above`
}
```

You should respond to these messages in the following way:

- All responses should be a JSON string with the form `{value: ...}`

- To a ping you should return any amount of data back, as quickly as possible. For example, you can send back `"{value: 0}"`, as it is a small, valid object. Pings are used both to benchmark latency and to ensure a connection is still alive.
- To a call you should respond with an object representing the player’s move for the given call. The object should be an encoding that the `shared.message_Connection.Decoder` understands. For example, since a chess AI can return either a string or a move, we can have our player response either be:
  - `{value: "e2e4"}`
  - `{value: {__custom_type: "chess_move", uci:"e2e4"}}`

Responses cannot be taken back and are interpreted as needed. This means you should not send more than one response to a message as, for example, if you sent two responses to a “call” and then the next message you got was a “ping”, your second response to the “call” would be interpreted as your response to the “ping”.

