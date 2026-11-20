#!/bin/sh
# A runner that replays a stored patch where an agent would have worked, so one diff can be
# graded as often as needed. Called in the clone like any runner: replay.sh PATCH MODEL
exec git apply "$1"
