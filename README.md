# submission-runner
A sandboxed python executer for user's submissions


# Documentation

## Environment variables
 - `SANDBOX_PYTHON_TIMEOUT` gives the total time that python is allowed to execute for. Eg. '10s'
 - `SANDBOX_CONTAINER_TIMEOUT` gives the overall timeout for containers managed by the sandbox api
   before they are killed in seconds, eg '10'. Should be about the same as `SANDBOX_PYTHON_TIMEOUT`
 - `SANDBOX_API_DEBUG` enables debug mode in Flask
 - `SANDBOX_MEM_LIMIT` is per container, given in the form 100000b, 1000k, 128m, 1g, etc
 - `SANDBOX_NANO_CPUS` is the CPU quota in units of 1e-9 CPUs.
 - `SANDBOX_SCRIPTS_VOLUME` is the name of the volume containing the scripts that are able to be run to evaluate the submissions

## Running the REST api
This container needs access to creating new sibling containers
and so should either be run with `-v /var/run/docker.sock:/var/run/docker.sock` to let
the containers be run as siblings, or with a dind sibling with `--privileged` if the containers should be
run as children

## Folder structure
The folders `runner` and `shared` are both present on the runner container.
The folders `sandbox-scripts` and `shared` are both present on the sandbox container.
In both, the `shared` folder will appear inside the `runner` or `sandbox-scripts` folder.