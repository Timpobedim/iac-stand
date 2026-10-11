# Три сегмента вместо одной общей сети: nginx — на edge и app, сервис — на app и db,
# базы — только на db. Сегменты app и db внутренние: из них нет выхода наружу,
# а с хоста в них не попасть ничем, кроме nginx.
#
# Шлюз задан явно: Docker дописывает его сам, и без него провайдер видит разницу при каждом
# plan — и пересоздаёт сеть, а с ней все подключённые контейнеры, включая базы.

resource "docker_network" "edge" {
  name = "${var.prefix}-edge"
  ipam_config {
    subnet  = var.subnets.edge
    gateway = cidrhost(var.subnets.edge, 1)
  }
}

resource "docker_network" "app" {
  name     = "${var.prefix}-app"
  internal = true
  ipam_config {
    subnet  = var.subnets.app
    gateway = cidrhost(var.subnets.app, 1)
  }
}

resource "docker_network" "db" {
  name     = "${var.prefix}-db"
  internal = true
  ipam_config {
    subnet  = var.subnets.db
    gateway = cidrhost(var.subnets.db, 1)
  }
}
