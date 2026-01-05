#!/usr/bin/env bash

set -euo pipefail

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL env var is required" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${ROOT_DIR}/backups"
mkdir -p "${BACKUP_DIR}"

TIMESTAMP="$(date -u +'%Y%m%d_%H%M%S')"
OUTPUT_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.dump"

echo "Creating backup at ${OUTPUT_FILE}"
pg_dump --format=custom "${DATABASE_URL}" -f "${OUTPUT_FILE}"
echo "Backup completed"
