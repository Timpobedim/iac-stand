#!/usr/bin/env bash
# Создать .env со случайными паролями, если его ещё нет. Файл в .gitignore: пароли
# не попадают в репозиторий, а у каждого, кто разворачивает стенд, — свои.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
    echo ".env уже есть — оставляю как есть"
    exit 0
fi

# /dev/urandom и base64 есть и в Linux, и в Git Bash; python3 в Git Bash бывает заглушкой Microsoft Store.
secret() { head -c 24 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n'; }

# Группа владельца сокета Docker: 0 на Docker Desktop, группа docker на Linux.
gid=0
if [[ -S /var/run/docker.sock ]] && stat -c %g /var/run/docker.sock > /dev/null 2>&1; then
    gid=$(stat -c %g /var/run/docker.sock)
fi

umask 077
cat > .env <<EOF
JENKINS_ADMIN_PASSWORD=$(secret)
TFSTATE_PASSWORD=$(secret)
DOCKER_SOCKET_GID=${gid}
EOF
echo ".env создан; пароль Jenkins (пользователь admin) — в нём"
