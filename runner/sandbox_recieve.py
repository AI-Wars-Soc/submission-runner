import re
import json

_message_p = re.compile('^([A-Z_]+):(.*);;$')


class Receiver:
    def __init__(self, output: str):
        self.key = None
        self.received = self._process_output(output)

    def _process_output(self, output: str):
        lines = output.split("\n")

        for line in lines:
            line = line.strip()
            if line.isspace() or line == "":
                continue

            yield self._process_line(line)

    def _process_line(self, line: str):
        # Check for special messages
        if line == "Killed":
            return {"type": "PROCESS_KILLED", "data": None}

        # Check for commands
        match = _message_p.match(line)

        # No match => assume print statement
        if match is None:
            return {"type": "PRINT", "data": line}

        command = match.group(1)
        args = [s.strip() for s in match.group(2).split(";")]

        if command == "NEW_KEY_EVENT":
            if self.key is not None:
                return {"type": "ERROR_INVALID_NEW_KEY", "data": args[0]}
            self.key = json.loads(args[0])
            return {"type": "NEW_KEY", "data": args[0]}
        elif command == "MESSAGE_EVENT":
            sent_key = json.loads(args[0])
            if sent_key != self.key:
                return {"type": "ERROR_INVALID_ATTACHED_KEY", "data": args[0]}
            return {"type": "MESSAGE", "data": args[1]}

        return {"type": "ERROR_INVALID_MESSAGE_TYPE", "data": command}
