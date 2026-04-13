#!/bin/bash
# LedgerMind Stop Hook (VS Code Agent)
if [ "$LEDGERMIND_BYPASS_HOOKS" = "1" ]; then exit 0; fi
export PYTHONPATH="/home/stanislav/Проекты/ledgermind/src":$PYTHONPATH
cat | ledgermind-mcp bridge-sync --path "/home/stanislav/Проекты/.ledgermind" --cli vscode-agent --stdin
