#!/usr/bin/env bash
# deploy.sh — install the multi-agent research pipeline as a systemd service.
#
#   sudo bash deploy.sh                 # install + start + health check
#   sudo bash deploy.sh --name marp-x --port 18088
#         bash deploy.sh --dry-run      # print the rendered unit, change nothing
#   sudo bash deploy.sh --uninstall     # stop, disable and remove the unit
#
# Idempotent: re-running upgrades the venv, re-renders the unit and restarts.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_TEMPLATE="$REPO_DIR/systemd/multi-agent-research.service"
SERVICE_NAME="multi-agent-research"
PORT="8088"
RUN_USER="${SUDO_USER:-$(id -un)}"
DRY_RUN=0
UNINSTALL=0

usage() {
  sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --name)      SERVICE_NAME="${2:?--name needs a value}"; shift 2 ;;
    --port)      PORT="${2:?--port needs a value}"; shift 2 ;;
    --user)      RUN_USER="${2:?--user needs a value}"; shift 2 ;;
    --dry-run|-n) DRY_RUN=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help)   usage; exit 0 ;;
    *)           echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

render_unit() {
  sed -e "s|@REPO_DIR@|${REPO_DIR}|g" \
      -e "s|@RUN_USER@|${RUN_USER}|g" \
      -e "s|@PORT@|${PORT}|g" \
      "$UNIT_TEMPLATE"
}

# Run a command as the service user (so files are not owned by root).
as_user() {
  if [ "$(id -u)" = "0" ] && [ "$RUN_USER" != "root" ]; then
    sudo -u "$RUN_USER" -- "$@"
  else
    "$@"
  fi
}

if [ ! -f "$UNIT_TEMPLATE" ]; then
  echo "ERROR: unit template not found: $UNIT_TEMPLATE" >&2
  exit 1
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "== dry run: no changes will be made =="
  echo "repo dir   : $REPO_DIR"
  echo "service    : $SERVICE_NAME"
  echo "run as user: $RUN_USER"
  echo "port       : $PORT"
  echo "unit path  : $UNIT_PATH"
  echo
  echo "----- ${UNIT_PATH} -----"
  render_unit
  echo "-------------------------"
  echo
  echo "would then run:"
  echo "  systemctl daemon-reload && systemctl enable --now ${SERVICE_NAME}"
  echo "  curl -fsS http://127.0.0.1:${PORT}/health"
  exit 0
fi

if [ "$(id -u)" != "0" ]; then
  echo "ERROR: installing a systemd unit needs root. Re-run with sudo," >&2
  echo "       or use --dry-run to preview the unit." >&2
  exit 1
fi
for cmd in systemctl sed curl; do
  command -v "$cmd" >/dev/null || { echo "ERROR: missing required command: $cmd" >&2; exit 1; }
done

if [ "$UNINSTALL" = "1" ]; then
  echo "==> stopping and removing ${SERVICE_NAME}"
  systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
  rm -f "$UNIT_PATH"
  systemctl daemon-reload
  echo "removed $UNIT_PATH"
  exit 0
fi

echo "==> 1/5 virtualenv"
if [ ! -x "$REPO_DIR/.venv/bin/python" ]; then
  as_user python3 -m venv "$REPO_DIR/.venv"
fi
as_user "$REPO_DIR/.venv/bin/pip" install --quiet --upgrade pip
as_user "$REPO_DIR/.venv/bin/pip" install --quiet -r "$REPO_DIR/requirements.txt"

echo "==> 2/5 environment file"
if [ ! -f "$REPO_DIR/.env" ]; then
  install -m 600 -o "$RUN_USER" "$REPO_DIR/.env.example" "$REPO_DIR/.env"
  echo "    created $REPO_DIR/.env from .env.example"
  echo "    NOTE: edit it and set DEEPSEEK_API_KEY, then re-run to restart."
else
  echo "    $REPO_DIR/.env already present (left untouched)"
fi

echo "==> 3/5 systemd unit"
render_unit > "$UNIT_PATH"
chmod 644 "$UNIT_PATH"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null

echo "==> 4/5 start"
systemctl restart "$SERVICE_NAME"

echo "==> 5/5 health check"
for _ in $(seq 1 15); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    echo "    $(curl -fsS "http://127.0.0.1:${PORT}/health")"
    echo "installed: ${SERVICE_NAME} (active, port ${PORT})"
    exit 0
  fi
  sleep 1
done

echo "ERROR: service did not answer on http://127.0.0.1:${PORT}/health within 15s" >&2
systemctl --no-pager --full status "$SERVICE_NAME" >&2 || true
exit 1
