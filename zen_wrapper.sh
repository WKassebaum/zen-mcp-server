#!/bin/bash
# Zen CLI Wrapper - Adds stdin support for Claude-friendly usage
# Usage:
#   echo "code" | zen_wrapper.sh analyze --analysis-type architecture
#   cat file.py | zen_wrapper.sh debug "issue description"

COMMAND=$1
shift

# Check if stdin has data
if [ -t 0 ]; then
    # No stdin, pass through to regular zen
    zen "$COMMAND" "$@"
else
    # Read stdin to temporary file
    TMPFILE=$(mktemp /tmp/zen_stdin.XXXXXX)
    cat > "$TMPFILE"

    # Add the temp file as -f argument
    zen "$COMMAND" -f "$TMPFILE" "$@"

    # Clean up
    rm "$TMPFILE"
fi