#!/bin/bash
if timeout $SANDBOX_COMMAND_TIMEOUT python3 /home/sandbox/sandbox/$1 || true ;
then
  echo "Done" ;
else
  echo "Timeout" ;
fi ;