#!/bin/sh
set -e

black lfcircle.py --check
isort lfcircle.py --check
mypy lfcircle.py
ruff check lfcircle.py
