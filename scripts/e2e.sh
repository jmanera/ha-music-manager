#!/usr/bin/env bash
# Real Home Assistant + the app image + a fake slskd, on a private Docker network.
# Usage: make e2e   (HA_VERSION=2026.10.4 IMAGE=ha-music-manager:dev by default)
set -euo pipefail

cd "$(dirname "$0")/.."
HA_VERSION=${HA_VERSION:-2026.10.4}
IMAGE=${IMAGE:-ha-music-manager:dev}
NET=hmm-e2e
CONFIG=$(mktemp -d)

cleanup() {
    docker rm -f hmm-e2e-ha hmm-e2e-app hmm-e2e-fake >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
    # Home Assistant writes its config as root inside the container.
    docker run --rm -v "$CONFIG":/config alpine rm -rf /config/* /config/.storage >/dev/null 2>&1 || true
    rmdir "$CONFIG" 2>/dev/null || true
}
trap cleanup EXIT
cleanup
CONFIG=$(mktemp -d)

docker network create "$NET" >/dev/null
docker run -d --name hmm-e2e-fake --network "$NET" -e FAKE_SLSKD_HOST=0.0.0.0 \
    -v "$PWD/scripts:/scripts:ro" "$IMAGE" python /scripts/fake_slskd.py >/dev/null
docker run -d --name hmm-e2e-app --network "$NET" --network-alias music-app \
    -e HMM_SLSKD_URL=http://hmm-e2e-fake:5031 -e HMM_SLSKD_API_KEY=demo \
    -e HMM_SOULSEEK_USERNAME=e2e "$IMAGE" >/dev/null
docker run -d --name hmm-e2e-ha --network "$NET" -p 127.0.0.1:18123:8123 \
    -v "$CONFIG:/config" -v "$PWD/custom_components:/config/custom_components:ro" \
    "ghcr.io/home-assistant/home-assistant:$HA_VERSION" >/dev/null

for _ in $(seq 30); do
    key=$(docker exec hmm-e2e-app cat /data/integration_key 2>/dev/null || true)
    [ -n "$key" ] && break
    sleep 1
done

E2E_APP_KEY=$key uv --directory integration_tests run python e2e.py || {
    echo "--- Home Assistant log ---"
    docker logs hmm-e2e-ha 2>&1 | grep -iE "music_manager|error" | tail -30
    echo "--- app log ---"
    docker logs hmm-e2e-app 2>&1 | tail -20
    exit 1
}

warnings=$(docker logs hmm-e2e-ha 2>&1 | grep -i music_manager | grep -iE "warn|deprecat|error" | grep -v "has not been tested by Home Assistant" || true)
if [ -n "$warnings" ]; then
    echo "--- Home Assistant warnings about music_manager ---"
    echo "$warnings"
fi
