#!/usr/bin/env bash

set -euo pipefail

DRY_RUN=false
TARGET_DIR="."

usage() {
    echo "Usage: $0 [-n] [directory]"
    echo "  -n    Dry run (show what would be done)"
    exit 1
}

# Parse options
while getopts ":n" opt; do
  case $opt in
    n) DRY_RUN=true ;;
    *) usage ;;
  esac
done

shift $((OPTIND - 1))

if [ $# -gt 0 ]; then
    TARGET_DIR="$1"
fi

echo "Scanning directory: $TARGET_DIR"
echo

find "$TARGET_DIR" -type l | while read -r symlink; do
    if [ ! -e "$symlink" ]; then
        echo "Skipping broken symlink: $symlink"
        continue
    fi

    real_path=$(readlink -f "$symlink")

    if [ ! -f "$real_path" ]; then
        echo "Skipping (not a regular file): $symlink -> $real_path"
        continue
    fi

    echo "Replacing: $symlink -> $real_path"

    if [ "$DRY_RUN" = false ]; then
        tmp_file=$(mktemp)
        cp -p "$real_path" "$tmp_file"
        rm "$symlink"
        mv "$tmp_file" "$symlink"
    fi
done

echo
echo "Done."