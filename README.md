# submission-runner
A sandboxed python executer for user's submissions


# Documentation

## Environment variables
 - `SANDBOX_PYPY_HEAPSIZE` and `SANDBOX_PYPY_TIMEOUT` give the parameters given to each PyPy instance
 - `SANDBOX_API_DEBUG` enables debug mode in Flask

## Running sandbox
The sandbox will attempt to run '`/exec/main.py`'. Any OS calls are put into stdout, 
and should either be replied to on stdin or the container should be halted if the request is not allowed.

In normal execution, all of these calls should probably be reported back to the user in the form of an error code

Pip modules to install can be given in sandbox/pip-requirements.txt

## Running the REST api
The REST API (also written in python) needs access to creating new sibling containers
and so should be run with `-v /var/run/docker.sock:/var/run/docker.sock`