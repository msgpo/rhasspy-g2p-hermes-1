#!/usr/bin/env bash
this_dir="$( cd "$( dirname "$0" )" && pwd )"
venv="${this_dir}/.venv"

if [[ ! -d "${venv}" ]]; then
    echo "Missing virtual environment at ${venv}"
    echo 'Did you run "make venv"?'
    exit 1
fi

export PATH="${venv}/bin:${PATH}"
export LD_LIBRARY_PATH="${venv}/lib:${LD_LIBRARY_PATH}"
