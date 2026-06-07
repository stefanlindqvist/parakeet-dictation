#!/bin/sh
# infra/runner-dictation/entrypoint.sh
#
# Registers and starts the gitea-runner daemon.
# Deployed to CT 102 at /srv/docker/runner-dictation/entrypoint.sh,
# bind-mounted over the container image's /entrypoint.sh.
#
# On every startup:
#   1. Installs the lab CA cert (so runner can verify gitea.home.lan TLS).
#   2. Wipes any previous .runner registration and re-registers with Gitea.
#   3. Starts the runner daemon.

set -eu

: "${GITEA_INSTANCE_URL:?GITEA_INSTANCE_URL env var is required}"
: "${GITEA_RUNNER_REGISTRATION_TOKEN:?GITEA_RUNNER_REGISTRATION_TOKEN env var is required}"
RUNNER_NAME_VAL="${GITEA_RUNNER_NAME:-ct102-runner-dictation}"
WORK_DIR="/data"

# Determine binary name (renamed from act_runner to gitea-runner at v1.0.0)
if command -v gitea-runner >/dev/null 2>&1; then
    RUNNER_BIN=gitea-runner
else
    RUNNER_BIN=act_runner
fi

# Install lab internal CA cert so runner trusts gitea.home.lan TLS
if [ -f /etc/ssl/certs-extra/lab-ca.crt ]; then
    if command -v update-ca-certificates >/dev/null 2>&1; then
        mkdir -p /usr/local/share/ca-certificates
        cp /etc/ssl/certs-extra/lab-ca.crt /usr/local/share/ca-certificates/lab-ca.crt
        update-ca-certificates > /dev/null 2>&1
    else
        # Alpine fallback: append directly to system cert bundle
        cat /etc/ssl/certs-extra/lab-ca.crt >> /etc/ssl/certs/ca-certificates.crt
    fi
    echo "[entrypoint] Lab CA cert installed."
fi

cd "${WORK_DIR}"

# Wipe previous registration to avoid stale credentials after container rebuild
rm -f .runner

echo "[entrypoint] Registering ${RUNNER_BIN} as '${RUNNER_NAME_VAL}'..."
"${RUNNER_BIN}" register \
    --no-interactive \
    --instance "${GITEA_INSTANCE_URL}" \
    --token "${GITEA_RUNNER_REGISTRATION_TOKEN}" \
    --name "${RUNNER_NAME_VAL}" \
    --labels "${GITEA_RUNNER_LABELS:-self-hosted,ubuntu-latest:docker://catthehacker/ubuntu:act-latest,dictation:docker://catthehacker/ubuntu:act-latest}"

echo "[entrypoint] Starting daemon..."
exec "${RUNNER_BIN}" daemon --config /etc/act_runner/config.yaml
