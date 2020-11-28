# submission-runner
A sandboxed python executer for user's submissions


# Documentation

## Environment variables
 - `SANDBOX_PYPY_HEAPSIZE` and `SANDBOX_PYPY_TIMEOUT` give the parameters given to each PyPy instance
 - `SANDBOX_API_DEBUG` enables debug mode in Flask
 - `SANDBOX_API_TIMEOUT` gives the overall timeout for containers managed by the sandbox api before they are killed
 - `SANDBOX_CPU_RT_RUNTIME_MICROSECONDS` gives the total amount of realtime CPU time a container can use before it is killed
 - `SANDBOX_MEM_LIMIT` is per container, given in the form 100000b, 1000k, 128m, 1g, etc
 - `SANDBOX_NANO_CPUS` is the CPU quota in units of 1e-9 CPUs.

## Running the REST api
The REST API (also written in python) needs access to creating new sibling containers
and so should be run with `-v /var/run/docker.sock:/var/run/docker.sock`