#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

cp -n .env.example .env || true

if ! command -v uv >/dev/null 2>&1; then
  echo "[install-local] missing required tool: uv"
  echo "Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

uv venv .venv
uv pip install --python .venv/bin/python -r services/orchestrator/requirements.txt
uv pip install --python .venv/bin/python -r services/orchestrator/requirements-dev.txt

npm --prefix apps/web ci

BIN_DIR="${HOME}/.local/bin"
SYNCOR_BIN="${BIN_DIR}/syncore"

mkdir -p "${BIN_DIR}"
cat >"${SYNCOR_BIN}" <<EOF
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT}"

case "\${1:-dev}" in
  install)
    shift
    exec bash "\${REPO_ROOT}/install.sh" "\$@"
    ;;
  db-init)
    shift
    exec bash "\${REPO_ROOT}/db-init.sh" "\$@"
    ;;
  dev|workspace)
    shift
    exec bash "\${REPO_ROOT}/dev.sh" "\$@"
    ;;
  demo-local)
    shift
    exec bash "\${REPO_ROOT}/scripts/demo_local_flow.sh" "\$@"
    ;;
  *)
    echo "Usage: syncore [install|db-init|dev|workspace|demo-local]"
    exit 2
    ;;
esac
EOF
chmod +x "${SYNCOR_BIN}"
ln -sf "${SYNCOR_BIN}" "${BIN_DIR}/Syncore"

if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
  echo "[install-local] add ${BIN_DIR} to PATH to run 'syncore' globally:"
  echo "  export PATH=\"${BIN_DIR}:\$PATH\""
fi

echo "[install-local] dependencies installed via uv-managed .venv"
echo "[install-local] CLI installed at ${SYNCOR_BIN}"
