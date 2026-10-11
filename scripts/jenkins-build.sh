#!/usr/bin/env bash
# Запустить задачу iac-stand и дождаться результата — изнутри контейнера Jenkins:
#   docker compose exec jenkins bash /src/scripts/jenkins-build.sh [BAD_RELEASE=true]
# Пароль берётся из окружения контейнера и наружу не выводится.
set -euo pipefail
JENKINS=http://127.0.0.1:8080
JOB=iac-stand
AUTH="admin:${JENKINS_ADMIN_PASSWORD}"
PARAMS="${1:-BAD_RELEASE=false}"
BUILD="${2:-}"   # номер уже запущенной сборки — только дождаться её

jar=$(mktemp)
trap 'rm -f "$jar"' EXIT
crumb=$(curl -sf -c "$jar" -u "$AUTH" "$JENKINS/crumbIssuer/api/json" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["crumbRequestField"] + ":" + d["crumb"])')

# Задача создаётся из casc.yaml; параметры появляются у неё после первого чтения Jenkinsfile.
if [[ -n "$BUILD" ]]; then queue=""; else
queue=$(curl -sf -b "$jar" -u "$AUTH" -H "$crumb" -X POST -D - -o /dev/null \
    "$JENKINS/job/$JOB/buildWithParameters?$PARAMS" | tr -d '\r' | awk '/^[Ll]ocation:/ {print $2}')
echo "в очереди: $queue"
fi

build=""
[[ -n "$BUILD" ]] && build="$JENKINS/job/$JOB/$BUILD/"
until [[ -n "$build" ]]; do
    sleep 2
    build=$(curl -sf -u "$AUTH" "${queue}api/json" \
        | python3 -c 'import json,sys; e=json.load(sys.stdin).get("executable"); print(e["url"] if e else "")')
done
# Jenkins отдаёт адрес с внешним портом (casc.yaml: location.url) — внутри контейнера он другой.
build="$JENKINS/${build#*://*/}"
echo "сборка: $build"

result=""
until [[ -n "$result" && "$result" != "None" ]]; do
    sleep 5
    result=$(curl -sf -u "$AUTH" "${build}api/json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"])')
done
curl -sf -u "$AUTH" "${build}consoleText" > /tmp/console.txt
grep -E "^\[Pipeline\] \{ \(|passed|failed|Apply complete|ok=|Finished:" /tmp/console.txt | tail -30
echo "результат: $result"
[[ "$result" == "SUCCESS" ]]
