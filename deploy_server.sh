#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/projects/ArxivPaper4"
TARGET=""
INSTALL_NPM=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --install-npm)
      INSTALL_NPM=true
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

case "$TARGET" in
  view|mobile|both|backend) ;;
  *)
    echo "--target must be one of: view, mobile, both, backend" >&2
    exit 2
    ;;
esac

build_client() {
  local label="$1"
  local directory="$2"

  echo "==== Building ${label} ===="
  cd "${PROJECT_ROOT}/${directory}"

  if [[ "$INSTALL_NPM" == true ]]; then
    npm install
  fi

  chmod +x node_modules/.bin/vite
  chmod +x node_modules/.bin/tsc
  chmod +x node_modules/typescript/bin/tsc
  npm run build
  test -d dist
  ls -la dist
}

case "$TARGET" in
  view)
    build_client "View" "View"
    ;;
  mobile)
    build_client "mobile_new" "mobile_new"
    ;;
  both)
    build_client "View" "View"
    build_client "mobile_new" "mobile_new"
    ;;
  backend)
    echo "==== Backend-only deployment: skipping frontend builds ===="
    ;;
esac

echo "==== Restarting services ===="
systemctl restart arxiv-api
nginx -t
systemctl reload nginx
systemctl is-active --quiet arxiv-api
systemctl is-active --quiet nginx

echo "DEPLOY_OK target=${TARGET} install_npm=${INSTALL_NPM}"
