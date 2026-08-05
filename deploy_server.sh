#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/projects/ArxivPaper4"
TARGET=""
INSTALL_NPM=false
PREBUILT=false
SERVICE_USER="ai4papers"
SERVICE_GROUP="ai4papers"

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

prepare_api_runtime_permissions() {
  local server_root="${PROJECT_ROOT}/Sever"
  local runtime_dirs=(
    "${server_root}/data"
    "${server_root}/database"
    "${server_root}/logs"
  )
  local paper_list="${server_root}/config/paperList.json"

  if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /nonexistent --shell /sbin/nologin "$SERVICE_USER"
  fi

  for runtime_dir in "${runtime_dirs[@]}"; do
    install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$runtime_dir"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$runtime_dir"
    find "$runtime_dir" -type d -exec chmod u+rwx {} +
  done

  touch "$paper_list"
  chown "$SERVICE_USER:$SERVICE_GROUP" "$paper_list"
  chmod u+rw,go-rwx "$paper_list"
}

api_is_ready() {
  local attempt
  for attempt in {1..20}; do
    if systemctl is-active --quiet arxiv-api \
      && curl --fail --silent --show-error --max-time 5 \
        "http://127.0.0.1:8000/api/papers?date=$(date +%F)" \
        --output /dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

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
echo "==== Preparing dedicated API service account ===="
prepare_api_runtime_permissions
API_SERVICE_SOURCE="${PROJECT_ROOT}/deploy/systemd/arxiv-api.service"
API_SERVICE_TARGET="/etc/systemd/system/arxiv-api.service"
API_SERVICE_BACKUP="${API_SERVICE_TARGET}.ai4papers-deploy-backup"
if [[ -f "$API_SERVICE_SOURCE" ]]; then
  echo "==== Installing API service unit ===="
  if [[ -f "$API_SERVICE_TARGET" ]]; then
    cp -f "$API_SERVICE_TARGET" "$API_SERVICE_BACKUP"
  fi
  install -m 0644 "$API_SERVICE_SOURCE" "$API_SERVICE_TARGET"
  systemctl daemon-reload
  systemctl enable arxiv-api.service
fi
if ! systemctl restart arxiv-api || ! api_is_ready; then
  echo "API restart failed; restoring the previous service unit." >&2
  if [[ -f "$API_SERVICE_BACKUP" ]]; then
    mv -f "$API_SERVICE_BACKUP" "$API_SERVICE_TARGET"
  else
    rm -f "$API_SERVICE_TARGET"
  fi
  systemctl daemon-reload
  systemctl restart arxiv-api || true
  api_is_ready || true
  exit 1
fi
rm -f "$API_SERVICE_BACKUP"

BACKUP_SERVICE_SOURCE="${PROJECT_ROOT}/deploy/systemd/ai4papers-db-backup.service"
BACKUP_TIMER_SOURCE="${PROJECT_ROOT}/deploy/systemd/ai4papers-db-backup.timer"
if [[ -f "$BACKUP_SERVICE_SOURCE" && -f "$BACKUP_TIMER_SOURCE" ]]; then
  echo "==== Installing database backup timer ===="
  install -m 0644 "$BACKUP_SERVICE_SOURCE" /etc/systemd/system/ai4papers-db-backup.service
  install -m 0644 "$BACKUP_TIMER_SOURCE" /etc/systemd/system/ai4papers-db-backup.timer
  systemctl daemon-reload
  systemctl enable --now ai4papers-db-backup.timer
fi

HEALTH_SERVICE_SOURCE="${PROJECT_ROOT}/deploy/systemd/ai4papers-healthcheck.service"
HEALTH_TIMER_SOURCE="${PROJECT_ROOT}/deploy/systemd/ai4papers-healthcheck.timer"
if [[ -f "$HEALTH_SERVICE_SOURCE" && -f "$HEALTH_TIMER_SOURCE" ]]; then
  echo "==== Installing production healthcheck timer ===="
  install -m 0644 "$HEALTH_SERVICE_SOURCE" /etc/systemd/system/ai4papers-healthcheck.service
  install -m 0644 "$HEALTH_TIMER_SOURCE" /etc/systemd/system/ai4papers-healthcheck.timer
  systemctl daemon-reload
  systemctl enable --now ai4papers-healthcheck.timer
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
