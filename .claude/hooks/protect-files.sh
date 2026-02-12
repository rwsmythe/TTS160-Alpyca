#!/bin/bash
# PreToolUse hook: Block edits to vendored and binary files
# Protected: AlpycaDevice (upstream reference), ZWO SDK binaries, virtual environment

INPUT=$(cat)

if echo "$INPUT" | grep -qiE '"file_path"\s*:\s*"[^"]*(AlpycaDevice/|zwo_capture/sdk/|\.venv/)'; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Protected file: vendored code, SDK binary, or virtual environment. These files should not be edited directly."}}'
fi

exit 0
