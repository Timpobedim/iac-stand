# nginx — единственная точка входа. Порт открыт только на var.edge_bind (по умолчанию
# 127.0.0.1). Список экземпляров сервиса в его конфигурации ведёт Ansible при каждом
# выкате; Terraform кладёт стартовую конфигурацию «нет развёрнутой версии».

resource "docker_image" "nginx" {
  name         = var.nginx_image
  keep_locally = true
}

resource "docker_container" "nginx" {
  name    = "${var.prefix}-nginx"
  image   = docker_image.nginx.image_id
  restart = "unless-stopped"
  memory  = 128
  # Без swap: иначе Docker ставит swap = 2 × memory, и provider видит разницу при каждом plan.
  memory_swap = 128

  ports {
    internal = 8080
    external = var.edge_port
    ip       = var.edge_bind
  }

  upload {
    file    = "/etc/nginx/conf.d/default.conf"
    content = file("${path.module}/templates/nginx-empty.conf")
  }

  networks_advanced {
    name    = docker_network.edge.id
    aliases = ["nginx"]
  }

  networks_advanced {
    name = docker_network.app.id
  }

  healthcheck {
    test     = ["CMD-SHELL", "wget -qO- http://127.0.0.1:8080/nginx-health || exit 1"]
    interval = "3s"
    timeout  = "2s"
    retries  = 10
  }

  wait = true
}
