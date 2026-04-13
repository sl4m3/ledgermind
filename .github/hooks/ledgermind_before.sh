#!/bin/bash
# LedgerMind UserPromptSubmit Hook (VS Code Agent)
if [ "$LEDGERMIND_BYPASS_HOOKS" = "1" ]; then exit 0; fi
export PYTHONPATH="/home/stanislav/Проекты/ledgermind/src":$PYTHONPATH
cat | ledgermind-mcp bridge-context --path "/home/stanislav/Проекты/.ledgermind" --prompt "-" --cli vscode-agent --stdin
