#!/bin/bash
if ! timeout -k 3 $SANDBOX_COMMAND_TIMEOUT python3 /home/sandbox/sandbox/$1 ;
then
  echo "Timeout" ;
fi ;
echo "Done" ;