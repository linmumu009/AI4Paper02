#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/projects/ArxivPaper4"
TARGET=""
INSTALL_NPM=false
PREBUILT=false

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
    --prebuilt)
      PREBUILT=true
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

if [[ "$PREBUILT" == true && "$INSTALL_NPM" == true ]]; then
  echo "--prebuilt and --install-npm cannot be used together" >&2
  exit 2
fi

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

deploy_prebuilt() {
  local label="$1"
  local directory="$2"
  local archive="$3"
  local client_root="${PROJECT_ROOT}/${directory}"
  local stage="${client_root}/.dist-stage-$$"
  local backup="${client_root}/.dist-backup-$$"

  echo "==== Installing prebuilt ${label} artifact ===="
  test -f "$archive"
  rm -rf "$stage" "$backup"
  mkdir -p "$stage"
  tar -xzf "$archive" -C "$stage"
  test -f "$stage/dist/index.html"

  if [[ -d "$client_root/dist" ]]; then
    mv "$client_root/dist" "$backup"
  fi

  if mv "$stage/dist" "$client_root/dist"; then
    rm -rf "$backup" "$stage" "$archive"
  else
    if [[ -d "$backup" ]]; then
      mv "$backup" "$client_root/dist"
    fi
    rm -rf "$stage"
    exit 1
  fi

  ls -la "$client_root/dist"
}

case "$TARGET" in
  view)
    if [[ "$PREBUILT" == true ]]; then
      deploy_prebuilt "View" "View" "${PROJECT_ROOT}/.deploy/view-dist.tar.gz"
    else
      build_client "View" "View"
    fi
    ;;
  mobile)
    if [[ "$PREBUILT" == true ]]; then
      deploy_prebuilt "mobile_new" "mobile_new" "${PROJECT_ROOT}/.deploy/mobile-dist.tar.gz"
    else
      build_client "mobile_new" "mobile_new"
    fi
    ;;
  both)
    if [[ "$PREBUILT" == true ]]; then
      deploy_prebuilt "View" "View" "${PROJECT_ROOT}/.deploy/view-dist.tar.gz"
      deploy_prebuilt "mobile_new" "mobile_new" "${PROJECT_ROOT}/.deploy/mobile-dist.tar.gz"
    else
      build_client "View" "View"
      build_client "mobile_new" "mobile_new"
    fi
    ;;
  backend)
    echo "==== Backend-only deployment: skipping frontend builds ===="
    ;;
esac

echo "==== Restarting services ===="
systemctl restart arxiv-api

BACKUP_SERVICE_SOURCE="${PROJECT_ROOT}/deploy/systemd/ai4papers-db-backup.service"
BACKUP_TIMER_SOURCE="${PROJECT_ROOT}/deploy/systemd/ai4papers-db-backup.timer"
if [[ -f "$BACKUP_SERVICE_SOURCE" && -f "$BACKUP_TIMER_SOURCE" ]]; then
  echo "==== Installing database backup timer ===="
  install -m 0644 "$BACKUP_SERVICE_SOURCE" /etc/systemd/system/ai4papers-db-backup.service
  install -m 0644 "$BACKUP_TIMER_SOURCE" /etc/systemd/system/ai4papers-db-backup.timer
  systemctl daemon-reload
  systemctl enable --now ai4papers-db-backup.timer
fi

NGINX_SOURCE="${PROJECT_ROOT}/nginx/arxivpaper4.conf"
NGINX_TARGET="/etc/nginx/conf.d/arxivpaper4.conf"
NGINX_BACKUP="${NGINX_TARGET}.ai4papers-deploy-backup"

if [[ -f "$NGINX_SOURCE" ]]; then
  if [[ -f "$NGINX_TARGET" ]]; then
    cp -f "$NGINX_TARGET" "$NGINX_BACKUP"
  fi
  install -m 0644 "$NGINX_SOURCE" "$NGINX_TARGET"
fi

if ! nginx -t; then
  echo "Nginx validation failed; restoring the previous AI4Papers config." >&2
  if [[ -f "$NGINX_BACKUP" ]]; then
    mv -f "$NGINX_BACKUP" "$NGINX_TARGET"
    nginx -t || true
  fi
  exit 1
fi

rm -f "$NGINX_BACKUP"
systemctl reload nginx
systemctl is-active --quiet arxiv-api
systemctl is-active --quiet nginx

echo "DEPLOY_OK target=${TARGET} install_npm=${INSTALL_NPM} prebuilt=${PREBUILT}"
