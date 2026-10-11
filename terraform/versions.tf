terraform {
  required_version = ">= 1.16.0"

  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "4.6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "3.9.1"
    }
  }

  # Состояние — в PostgreSQL с блокировкой (pg_advisory_lock): два одновременных apply
  # не испортят его. Строка подключения — из переменной окружения PG_CONN_STR,
  # в репозитории её нет.
  backend "pg" {
    schema_name = "iac_stand"
  }
}

# Адрес Docker — из DOCKER_HOST или сокет по умолчанию.
provider "docker" {}
