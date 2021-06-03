#!/bin/bash
function runPython {
  python3 /home/sandbox/sandbox/$0 ;
  return 0 ;
}

export -f runPython

timeout -s SIGKILL $2 bash -c runPython $1
