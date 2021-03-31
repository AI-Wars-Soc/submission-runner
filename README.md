# submission-runner
A sandboxed python executer for user's submissions


# Documentation

## Environment variables
 - `SANDBOX_COMMAND_TIMEOUT` gives the total time that python is allowed to execute for. Eg. '10s'
 - `SANDBOX_CONTAINER_TIMEOUT` gives the overall timeout for containers before they kill themselves. Eg. '12s'
 - `SANDBOX_PARSER_TIMEOUT` gives the number of seconds that the parser will wait for the program to finish
   outputting before it kills the container, eg. '11'. This should be the primary timeout, and so should be a lot smaller
   than the other timeouts
 - `DEBUG` enables debug mode
 - `SANDBOX_MEM_LIMIT` is per container, given in the form 100000b, 1000k, 128m, 1g, etc
 - `SANDBOX_CPU_COUNT` is the total amount of cpu that the sandbox can use. For example, '0.5'
   means that the sandbox can use a maximum of 50% of one core
 - `DATABASE_CONNECTION` is the URL for the shared database connection
 - `GAMEMODE` is the gamemode to start the runner running, eg 'chess'
 - `GAME_OPTIONS` are the options for the game in json format. For a full list see `gamemodes.json`
 - `INITIAL_SCORE_MILLIS` gives the initial score for all users
 - `SCORE_TURBULENCE_MILLIS` gives the maximum score change for a single win or loss
 - `MATCHMAKERS` gives the number of independent threads creating and running matches. Minimum 2 so that one can run tests
 - `SECONDS_PER_RUN` gives the time to wait after each run

## Running the REST api
This container needs access to creating new sibling containers
and so should either be run with `-v /var/run/docker.sock:/var/run/docker.sock` to let
the containers be run as siblings, or with a dind sibling with `--privileged` if the containers should be
run as children

## Folder structure
The folders `runner` and `shared` are both present on the runner container.
The folders `sandbox` and `shared` are both present on the sandbox container.
In both, the `shared` folder will appear inside the `runner` or `sandbox` folder.
