#!/usr/bin/env bash
# Set or change the dashboard password on a deployed Copilot.
#
#   deploy/set-password.sh <ssh-target> [--dir PATH]
#
# Run it from your own terminal: it prompts for the password, hashes it on
# this machine, and sends only the hash to the server.
exec "$(dirname "${BASH_SOURCE[0]}")/deploy.sh" "$@" --set-password
