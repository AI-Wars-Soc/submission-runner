# submission-runner
A sandboxed python executer for user's submissions


# Documentation

## Environment variables
 - `SANDBOX_PYTHON_TIMEOUT` gives the total time that python is allowed to execute for. Eg. '10s'
 - `SANDBOX_CONTAINER_TIMEOUT` gives the total time that the container will live for independently, Eg. '20s'
 - `SANDBOX_API_DEBUG` enables debug mode in Flask
 - `SANDBOX_API_TIMEOUT` gives the overall timeout for containers managed by the sandbox api before they are killed
 - `SANDBOX_MEM_LIMIT` is per container, given in the form 100000b, 1000k, 128m, 1g, etc
 - `SANDBOX_NANO_CPUS` is the CPU quota in units of 1e-9 CPUs.
 - `SANDBOX_SCRIPTS_VOLUME` is the name of the volume containing the scripts that are able to be run to evaluate the submissions

## Running the REST api
The REST API (also written in python) needs access to creating new sibling containers
and so should either be run with `-v /var/run/docker.sock:/var/run/docker.sock` to let
the containers be run as siblings, or with a dind sibling with `--privileged` if the containers should be
run as children