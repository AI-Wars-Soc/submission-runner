import io
import tarfile
import threading

import docker
import docker.errors
import docker.types.daemon
import os
import re

import requests
from docker.models.containers import Container

from shared.gamemodes import Gamemode
from shared.messages import MessageType, Message, Receiver
from typing import Iterator
import logging

_client = docker.from_env()


class MissingEnvVarsError(RuntimeError):
    pass


class TimedContainer:
    """
    A container which lives for a maximum of `timeout`ms.
    Commands can be run on the container and files transferred to it,
    but all of this must be done within the timeout given.
    After this, the container will force close, with every message stream
    closing with a `ERROR_PROCESS_TIMEOUT` message
    """

    def __init__(self, timeout):
        self.timeout = timeout

        # Create container
        self._env_vars = TimedContainer._get_env_vars()
        self._container = TimedContainer._make_sandbox_container(self._env_vars)

        # Copy information
        self._copy_sandbox_scripts()

        # Create kill thread
        self.stopped = False
        self._kill_thread = threading.Thread(target=TimedContainer._timeout_method, args=(self, timeout,))
        self._kill_thread.setDaemon(True)
        self._kill_thread.start()
        self._killed_messages = []

    def stop(self):
        try:
            if self._container is not None and self._container.status in {"running", "created", "restarting", "paused"}:
                self._container.stop(timeout=3)
        except docker.errors.NotFound:
            pass
        finally:
            self._container = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    @staticmethod
    def _get_env_vars() -> dict:
        var_names = ['SANDBOX_COMMAND_TIMEOUT', 'SANDBOX_CONTAINER_TIMEOUT',
                     'SANDBOX_MEM_LIMIT', 'SANDBOX_CPU_COUNT']
        env_vars = {name: str(os.getenv(name)) for name in var_names}
        env_vars['PYTHONPATH'] = "/home/sandbox/"

        unset = list(filter(lambda v: env_vars[v] is None, env_vars.keys()))
        if len(unset) != 0:
            error = f"Required environment variables are unset {str(unset)}"
            raise MissingEnvVarsError(error)

        return env_vars

    @staticmethod
    def _make_sandbox_container(env_vars) -> Container:
        return _client.containers.run("aiwarssoc/sandbox",
                                      detach=True,
                                      remove=True,
                                      mem_limit=env_vars['SANDBOX_MEM_LIMIT'],
                                      memswap_limit=env_vars['SANDBOX_MEM_LIMIT'],
                                      cpu_period=100000,
                                      cpu_quota=int(100000 * float(env_vars['SANDBOX_CPU_COUNT'])),
                                      tty=True,
                                      network_mode='none',
                                      # read_only=True,  # marks all volumes as read only, just in case
                                      environment=env_vars,
                                      command="sh -c 'sleep $SANDBOX_CONTAINER_TIMEOUT'",
                                      user='sandbox',
                                      tmpfs={
                                          '/tmp': 'size=64M,uid=1000',
                                          '/var/tmp': 'size=64M,uid=1001'
                                      })

    @staticmethod
    def _compress_sandbox_files(fh):
        with tarfile.open(fileobj=fh, mode='w') as tar:
            tar.add("/exec/sandbox", arcname="sandbox")
            tar.add("/exec/shared", arcname="shared")

    def _copy_sandbox_scripts(self):
        with io.BytesIO() as fh:
            # Compress files to tar
            TimedContainer._compress_sandbox_files(fh)

            # Send
            self._container.put_archive("/home/sandbox/", fh.getvalue())

        # Fix ownership
        self._container.exec_run("chown -R sandbox:sandbox /home/sandbox/", user='root')
        self._container.exec_run("chmod -R ugo=rx /home/sandbox/", user='root')

    def _error(self, message_type: MessageType, **kwargs) -> Message:
        data = dict({'identifier': str(self)}, **kwargs)

        message = Message(message_type, data)

        logging.error("{}: {}".format(message_type, str(data)))

        return message

    @staticmethod
    def _timeout_method(container: 'TimedContainer', timeout: int):
        try:
            container._container.wait(timeout=timeout)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
            container._killed_messages.append(container._error(MessageType.ERROR_PROCESS_TIMEOUT))
            container.stop()

    @staticmethod
    def _get_lines(strings):
        line = []
        for string in strings:
            if string is None or string == "":
                continue
            string = str(string.decode())
            for char in string:
                if char == "\r" or char == "\n":
                    if len(line) != 0:
                        yield "".join(line)
                    line = []
                else:
                    line.append(char)

        if len(line) != 0:
            yield "".join(line)

    @staticmethod
    def _is_script_valid(script_name: str):
        script_name_rex = re.compile("^[a-zA-Z0-9_/]+\\.py$")
        return os.path.exists("/exec/sandbox/" + script_name) and script_name_rex.match(script_name) is not None

    def _run_unfiltered(self, script_name: str, extra_args: dict) -> Iterator[Message]:
        if extra_args is None:
            extra_args = dict()

        # Ensure that script is valid
        if not TimedContainer._is_script_valid(script_name):
            yield self._error(MessageType.ERROR_INVALID_ENTRY_FILE)
            return

        # Get env vars
        env_vars = {**self._env_vars, **extra_args}

        # Start script
        run_script_cmd = "./sandbox/run.sh '{path}'".format(path=script_name)
        (exit_code, stream) = self._container.exec_run(cmd=run_script_cmd,
                                                       user='sandbox',
                                                       stream=True,
                                                       environment=env_vars,
                                                       workdir="/home/sandbox/")

        # Process lines
        lines = TimedContainer._get_lines(stream)
        receiver = Receiver(lines)
        iterator = receiver.get_messages_iterator()
        yield from iterator

        yield from self._killed_messages

    @staticmethod
    def _is_submission_valid(submission_hash: str, submission_path: str):
        submission_hash_rex = re.compile("^[a-f0-9]+$")
        return os.path.exists(submission_path) and submission_hash_rex.match(submission_hash) is not None

    def copy_submission(self, submission_hash: str, container_dir: str):
        submission_path = f"/repositories/{submission_hash}.tar"
        # Ensure that submission is valid
        if not TimedContainer._is_submission_valid(submission_hash, submission_path):
            return self._error(MessageType.ERROR_INVALID_SUBMISSION)

        dest_path = os.path.join("/home/sandbox/sandbox", container_dir)
        with open(submission_path, 'rb') as f:
            data = f.read()
            self._container.put_archive(dest_path, data)

    def run(self, script_name: str, extra_args=None) -> Iterator[Message]:
        messages = self._run_unfiltered(script_name, extra_args)
        yield from Message.filter_middle_ends_to_prints(messages)

    def __str__(self):
        return f"TimedContainer<{self._container}>"


def run_in_sandbox(gamemode: Gamemode, submission_hashes=None, options=None) -> Iterator[Message]:
    """runs the given script in a sandbox and returns a result list.
    Each item in the list is of type 'Message' and is either output from the sandbox
    or an error while trying to run the sandbox.
    """
    script_name = gamemode.script

    if submission_hashes is None:
        submission_hashes = []
    if options is None:
        options = dict()
    logging.info("Request for script " + script_name)

    option_args = gamemode.create_env_vars(**options)

    timeout = int(os.getenv('SANDBOX_PARSER_TIMEOUT'))
    with TimedContainer(timeout) as container:
        for i, submission_hash in enumerate(submission_hashes):
            subdir = f"submission{i + 1}"
            container.copy_submission(submission_hash, subdir)

        yield from container.run(script_name, option_args)
