#!/usr/bin/env bash
set -euo pipefail

IMAGE="free-bot:latest"
CONTAINER="free-bot"
REBUILD=false
PERSIST_DB=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  -i, --image NAME         Docker image name (default: free-bot:latest)
  -c, --container NAME     Docker container name (default: free-bot)
  -r, --rebuild            Force rebuild image
  -p, --persist-db         Mount ./data and set DB_PATH for persistent SQLite
  -h, --help               Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--image) IMAGE="$2"; shift 2;;
    -c|--container) CONTAINER="$2"; shift 2;;
    -r|--rebuild) REBUILD=true; shift;;
    -p|--persist-db) PERSIST_DB=true; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "[free-bot] Docker not found. Install Docker and try again." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "[free-bot] .env not found. Copy .env.example to .env and set DISCORD_TOKEN (and optionally POLL_MINUTES)." >&2
  exit 1
fi

if $REBUILD || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "[free-bot] Building image '$IMAGE'..."
  docker build -t "$IMAGE" .
else
  echo "[free-bot] Using existing image '$IMAGE'."
fi

if id=$(docker ps -a --filter "name=^/${CONTAINER}$" -q); then
  if [[ -n "$id" ]]; then
    echo "[free-bot] Stopping/removing existing container '$CONTAINER'..."
    docker stop "$CONTAINER" >/dev/null || true
    docker rm "$CONTAINER" >/dev/null || true
  fi
fi

args=(run -d --name "$CONTAINER" --env-file .env --restart unless-stopped)

if $PERSIST_DB; then
  mkdir -p ./data
  host_path="$(pwd)/data"
  args+=( -v "${host_path}:/data" -e DB_PATH=/data/free_deals.sqlite3 )
fi

args+=( "$IMAGE" )

echo "[free-bot] Starting container '$CONTAINER'..."
docker "${args[@]}"
echo "[free-bot] Running. Logs: docker logs -f $CONTAINER"
echo "[free-bot] Stop/Remove: docker stop $CONTAINER; docker rm $CONTAINER"

