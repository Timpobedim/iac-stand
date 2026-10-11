# PostgreSQL: основная база и потоковая реплика. Пароли генерирует Terraform; они лежат
# только в состоянии (которое хранится в PostgreSQL, а не в git) и в окружении контейнеров.

resource "random_password" "postgres" {
  length  = 32
  special = false
}

resource "random_password" "replicator" {
  length  = 32
  special = false
}

resource "random_password" "app" {
  length  = 32
  special = false
}

resource "docker_image" "postgres" {
  name         = var.postgres_image
  keep_locally = true
}

resource "docker_volume" "primary" {
  name = "${var.prefix}-db-primary"
}

resource "docker_volume" "replica" {
  name = "${var.prefix}-db-replica"
}

locals {
  pg_hba = templatefile("${path.module}/templates/pg_hba.conf.tftpl", {
    db_subnet = var.subnets.db
  })
}

resource "docker_container" "primary" {
  name    = "${var.prefix}-db-primary"
  image   = docker_image.postgres.image_id
  restart = "unless-stopped"
  memory  = 512
  # Без swap: иначе Docker ставит swap = 2 × memory, и provider видит разницу при каждом plan.
  memory_swap = 512

  env = [
    "POSTGRES_PASSWORD=${random_password.postgres.result}",
    "POSTGRES_DB=orders",
    "REPLICATOR_PASSWORD=${random_password.replicator.result}",
  ]

  command = [
    "postgres",
    "-c", "wal_level=replica",
    "-c", "max_wal_senders=5",
    "-c", "max_replication_slots=5",
    "-c", "hba_file=/etc/postgresql/pg_hba.conf",
  ]

  upload {
    file    = "/etc/postgresql/pg_hba.conf"
    content = local.pg_hba
  }

  upload {
    file       = "/docker-entrypoint-initdb.d/10-replication.sh"
    content    = file("${path.module}/templates/primary-init.sh")
    executable = true
  }

  networks_advanced {
    name    = docker_network.db.id
    aliases = ["db-primary"]
  }

  volumes {
    volume_name    = docker_volume.primary.name
    container_path = "/var/lib/postgresql/data"
  }

  healthcheck {
    test         = ["CMD-SHELL", "pg_isready -U postgres -d orders"]
    interval     = "2s"
    timeout      = "3s"
    retries      = 15
    start_period = "5s"
  }

  wait         = true
  wait_timeout = 90
}

resource "docker_container" "replica" {
  name    = "${var.prefix}-db-replica"
  image   = docker_image.postgres.image_id
  restart = "unless-stopped"
  memory  = 512
  # Без swap: иначе Docker ставит swap = 2 × memory, и provider видит разницу при каждом plan.
  memory_swap = 512

  env = [
    "PRIMARY_HOST=db-primary",
    "REPLICATOR_PASSWORD=${random_password.replicator.result}",
  ]

  entrypoint = ["/bin/sh", "/opt/replica-entrypoint.sh"]

  upload {
    file    = "/opt/replica-entrypoint.sh"
    content = file("${path.module}/templates/replica-entrypoint.sh")
  }

  upload {
    file    = "/etc/postgresql/pg_hba.conf"
    content = local.pg_hba
  }

  networks_advanced {
    name    = docker_network.db.id
    aliases = ["db-replica"]
  }

  volumes {
    volume_name    = docker_volume.replica.name
    container_path = "/var/lib/postgresql/data"
  }

  healthcheck {
    # Реплика здорова, только если она действительно в режиме восстановления.
    test         = ["CMD-SHELL", "psql -U postgres -tAc 'SELECT pg_is_in_recovery()' | grep -q t"]
    interval     = "2s"
    timeout      = "3s"
    retries      = 30
    start_period = "5s"
  }

  wait         = true
  wait_timeout = 120

  depends_on = [docker_container.primary]
}
