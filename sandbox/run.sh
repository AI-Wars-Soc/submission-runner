#!/bin/bash
function runPython {
  python3 /home/sandbox/sandbox/$0 ;
  return 0 ;
}

export -f runPython

if ! timeout -k 3 $SANDBOX_COMMAND_TIMEOUT bash -c runPython $1 ;
then
  echo "Timeout" ;
fi ;
echo "Done" ;