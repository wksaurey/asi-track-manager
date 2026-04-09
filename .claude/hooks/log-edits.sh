#!/bin/bash

# PostToolUse hook for Edit — logs each edited file path with timestamp.
# Review .claude/edit-log.md periodically to catch docs that need updating.

FILE_PATH=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

if [ -n "$FILE_PATH" ]; then
  # Make path relative to project root for readability
  REL_PATH="${FILE_PATH#$CLAUDE_PROJECT_DIR/}"
  echo "- [$TIMESTAMP] $REL_PATH" >> "$CLAUDE_PROJECT_DIR/.claude/edit-log.md"
fi

exit 0
