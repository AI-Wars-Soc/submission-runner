import io
import os
import re
import tarfile
import threading
from ssl import SSLSocket
from typing import Iterator, Optional

import docker
import docker.errors
import docker.types.daemon
import docker.utils.socket
import requests
from cuwais.config import config_file
from docker.models.containers import Container

from runner.logger import logger
from shared.message_connection import MessagePrintConnection
from shared.connection import Connection, ConnectionTimedOutError

DOCKER_IMAGE_NAME = "aiwarssoc/sandbox"
_client = docker.from_env()
_client.images.pull(DOCKER_IMAGE_NAME)


class InvalidEntryFile(RuntimeError):
    pass


class InvalidSubmissionError(RuntimeError):
    pass


class TimedContainer:
    """
    A container which lives for a maximum of `timeout`ms.
    Commands can be run on the container and files transferred to it,
    but all of this must be done within the timeout given.
    After this, the container will force close
    """
    _container: Optional[Container]

    def __init__(self, timeout: int, submission_hash: str):
        self.timeout = timeout
        self.submission_hash = submission_hash

        # Create container
        logger.debug(f"Creating container {self}")
        self._env_vars = TimedContainer._get_env_vars()
        self._container = TimedContainer._make_sandbox_container(self._env_vars)

        # Copy information
        logger.debug(f"Copying scripts {self}")
        self._copy_sandbox_scripts()
        logger.debug(f"Copying submission {self}")
        self._copy_submission(submission_hash)
        logger.debug(f"Locking down {self}")
        self._lock_down()

        # Kill thread
        self._timeout = timeout
        self._timed_out = False

        logger.debug(f"Done making timed container {self}")

    def _start_timer(self):
        logger.debug(f"Creating kill thread {self}")
        kill_thread = threading.Thread(target=TimedContainer._timeout_method, args=(self, self._timeout,))
        kill_thread.setDaemon(True)
        kill_thread.start()

    def stop(self):
        try:
            self._container.stop(timeout=0)
        except docker.errors.NotFound:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    @staticmethod
    def _get_env_vars() -> dict:
        env_vars = dict()
        env_vars['PYTHONPATH'] = "/home/sandbox/"
        env_vars['DEBUG'] = str(config_file.get("debug"))

        return env_vars

    @staticmethod
    def _make_sandbox_container(env_vars) -> Container:
        mem_limit = str(config_file.get("submission_runner.sandbox_memory_limit"))
        unrun_t = int(config_file.get('submission_runner.sandbox_unrun_timeout_seconds'))
        cpu_quota = int(100000 * float(config_file.get("submission_runner.sandbox_cpu_count")))
        return _client.containers.run(DOCKER_IMAGE_NAME,
                                      detach=True,
                                      remove=True,
                                      mem_limit=mem_limit,
                                      memswap_limit=mem_limit,
                                      cpu_period=100000,
                                      cpu_quota=cpu_quota,
                                      tty=False,
                                      stream=True,
                                      network_mode='none',
                                      cap_drop=["ALL"],
                                      # read_only=True,  # marks all volumes as read only, just in case
                                      environment=env_vars,
                                      command=f"sh -c 'sleep {unrun_t}'",
                                      user='sandbox',
                                      tmpfs={
                                          '/tmp': f'size=1M',
                                          '/var/tmp': f'size=1M',
                                          '/dev/shm': f'size=1M',
                                          '/run/lock': f'size=1M',
                                          '/var/lock': f'size=1M'
                                      })

    @staticmethod
    def _compress_sandbox_files(fh):
        with tarfile.open(fileobj=fh, mode='w') as tar:
            tar.add("./sandbox", arcname="sandbox")
            tar.add("./shared", arcname="shared")

    def _copy_sandbox_scripts(self):
        with io.BytesIO() as fh:
            # Compress files to tar
            TimedContainer._compress_sandbox_files(fh)

            # Send
            self._container.put_archive("/home/sandbox/", fh.getvalue())

    def _copy_submission(self, submission_hash: str):
        submission_path = f"/home/subrunner/repositories/{submission_hash}.tar"
        # Ensure that submission is valid
        if not TimedContainer._is_submission_valid(submission_hash, submission_path):
            raise InvalidSubmissionError(submission_hash)

        # Make destination
        dest_path = "/home/sandbox/submission"
        self._container.exec_run(f"mkdir {dest_path}", user='root')

        # Make required init file for python
        init_path = os.path.join(dest_path, "__init__.py")
        self._container.exec_run(f"touch {init_path}", user='root')

        with open(submission_path, 'rb') as f:
            data = f.read()
            self._container.put_archive(dest_path, data)

    def _lock_down(self):
        # Set write limits
        self._container.exec_run("chmod -R ugo=rx /home/sandbox/")  # TODO: Very slow (~2s) because of CoW?
        # logger.debug(self._container.exec_run("ls -alR /home/sandbox").output.decode())

    def _timeout_method(self, timeout: int):
        try:
            self._container.wait(timeout=timeout)
        except requests.exceptions.ReadTimeout:
            logger.debug(f"Killing thread due to timeout {self}")
            self._timed_out = True
            self.stop()
        except requests.exceptions.ConnectionError:
            pass

    @staticmethod
    def _read(socket, n=4096):
        """
        Reads at most n bytes from socket
        Pulled from docker API (docker.utils.socket) with the removal of the below lines
        because they cause infinite hanging
        TODO: See if there is a better solution to this
        """

        recoverable_errors = (docker.utils.socket.errno.EINTR, docker.utils.socket.errno.EDEADLK, docker.utils.socket.errno.EWOULDBLOCK)

        # if docker.utils.socket.six.PY3 and not isinstance(socket, docker.utils.socket.NpipeSocket):
            # docker.utils.socket.select.select([socket], [], [])

        try:
            if hasattr(socket, 'recv'):
                return socket.recv(n)
            if docker.utils.socket.six.PY3 and isinstance(socket, getattr(docker.utils.socket.pysocket, 'SocketIO')):
                return socket.read(n)
            return os.read(socket.fileno(), n)
        except EnvironmentError as e:
            if e.errno not in recoverable_errors:
                raise

    @staticmethod
    def _frames_iter_no_tty(socket):
        """
        Returns a generator of data read from the socket when the tty setting is
        not enabled.

        Taken from docker.utils.socket
        """
        while True:
            (stream, n) = docker.utils.socket.next_frame_header(socket)
            if n < 0:
                break
            while n > 0:
                result = TimedContainer._read(socket, n)
                if result is None:
                    continue
                data_length = len(result)
                if data_length == 0:
                    # We have reached EOF
                    return
                n -= data_length
                yield result.decode()

    @staticmethod
    def _get_lines(strings: Iterator[str]) -> Iterator[str]:
        line = []
        for string in strings:
            if string is None or string == b'' or string == "":
                continue
            for char in string:
                if char == "\r" or char == "\n":
                    if len(line) != 0:
                        yield "".join(line)
                    line = []
                else:
                    line.append(char)

        if len(line) != 0:
            yield "".join(line)

    def _add_timeout_exception(self, iterator):
        yield from iterator

        if self._timed_out:
            raise ConnectionTimedOutError()

    def _add_stop(self, iterator):
        yield from iterator

        self.stop()

    @staticmethod
    def _is_script_valid(script_name: str):
        script_name_rex = re.compile("^[a-zA-Z0-9_/]*$")
        return os.path.exists("./sandbox/" + script_name + ".py") and script_name_rex.match(script_name) is not None

    def run(self) -> Connection:
        # Start the timer
        self._start_timer()

        # Start script
        logger.debug(f"Running command in container {self}")
        run_t = int(config_file.get('submission_runner.sandbox_run_timeout_seconds'))
        run_script_cmd = f"./sandbox/run.sh 'play.py' {run_t}"
        socket: SSLSocket
        _, socket = self._container.exec_run(cmd=run_script_cmd,
                                             user='read_only_user',
                                             stream=True,
                                             socket=True,
                                             stdin=True,
                                             tty=False,
                                             environment=self._env_vars,
                                             workdir="/home/sandbox/")

        # Set up input to the container
        def send_handler(m: str):
            socket.write((m + "\n").encode())

        # Process output from the container
        logger.debug(f"Setting up output processing {self}")
        socket.settimeout(self.timeout)
        strings = TimedContainer._frames_iter_no_tty(socket)
        lines = TimedContainer._get_lines(strings)
        received = self._add_stop(self._add_timeout_exception(lines))

        logger.debug(f"Connecting {self}")
        return MessagePrintConnection(send_handler, received)

    @staticmethod
    def _is_submission_valid(submission_hash: str, submission_path: str):
        submission_hash_rex = re.compile("^[a-f0-9]+$")
        return os.path.exists(submission_path) and submission_hash_rex.match(submission_hash) is not None
