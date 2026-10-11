# Все шаги стенда. Выполняются внутри образа jenkins/Dockerfile — в пайплайне Jenkins
# или с машины разработчика: docker compose run --rm tools <цель>.
#
# Состояние Terraform — в PostgreSQL: строка подключения в переменной PG_CONN_STR.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
TF := terraform -chdir=terraform
VERSION ?= dev
BAD ?= false
PREFIX ?= stand
export ANSIBLE_CONFIG := $(CURDIR)/ansible/ansible.cfg
# Провайдеры скачиваются один раз на машину, а не в каждой сборке: быстрее и не зависит
# от того, ответил ли реестр Terraform именно сейчас.
export TF_PLUGIN_CACHE_DIR ?= $(HOME)/.terraform.d/plugin-cache
$(shell mkdir -p $(TF_PLUGIN_CACHE_DIR))

.PHONY: check lint unit init plan infra build deploy test up down

check: lint unit ## статические проверки и модульные тесты — без Docker и без состояния

lint:
	$(TF) fmt -check -recursive
	# Своя папка .terraform для проверок: без неё validate подхватит бэкенд из прошлого init
	# и пойдёт за состоянием, которое линтеру не нужно (и которого в стадии проверок нет).
	TF_DATA_DIR=.terraform-lint $(TF) init -backend=false -input=false > /dev/null
	TF_DATA_DIR=.terraform-lint $(TF) validate
	cd ansible && ansible-lint --offline -q deploy.yml teardown.yml
	ruff check app tests ansible/inventory scripts

unit:
	mkdir -p reports
	PYTHONPATH=app pytest -q app/tests tests/unit --junitxml=reports/unit.xml

init:
	$(TF) init -input=false -reconfigure

plan: init
	$(TF) plan -input=false -out=tfplan
	$(TF) show -json tfplan | python3 scripts/plan_guard.py

infra: plan ## сети, базы с репликой, nginx
	$(TF) apply -input=false tfplan
	@# Сразу после apply план обязан быть пустым. Иначе провайдер видит дрейф, которого нет,
	@# и следующий запуск что-то пересоздаст: так было со шлюзом сетей и с memory_swap.
	$(TF) plan -input=false -detailed-exitcode > /dev/null || { echo "после apply план не пуст — дрейф"; exit 1; }

build: ## образ сервиса заказов stand-app:$(VERSION)
	docker build -q -t stand-app:$(VERSION) app

deploy: ## миграции и поочерёдный выкат; BAD=true — учебная авария
	cd ansible && ansible-playbook -i inventory/terraform.py deploy.yml -e app_version=$(VERSION) -e bad_release=$(BAD)

test: ## проверка живого стенда: сети, репликация, порты, выкат без простоя, откат
	mkdir -p reports
	STAND_PREFIX=$(PREFIX) pytest -q tests/infra --junitxml=reports/infra.xml

up: build infra deploy test

down: ## снять сервис и всю инфраструктуру
	cd ansible && ansible-playbook -i inventory/terraform.py teardown.yml
	$(TF) destroy -input=false -auto-approve
