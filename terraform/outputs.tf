output "prefix" {
  value = var.prefix
}

output "networks" {
  description = "Имена сетей по сегментам"
  value = {
    edge = docker_network.edge.name
    app  = docker_network.app.name
    db   = docker_network.db.name
  }
}

output "subnets" {
  value = var.subnets
}

output "containers" {
  value = {
    nginx   = docker_container.nginx.name
    primary = docker_container.primary.name
    replica = docker_container.replica.name
  }
}

output "edge_url" {
  value = "http://${var.edge_bind}:${var.edge_port}"
}

output "app_db_password" {
  description = "Пароль роли сервиса в базе: роль создаёт Ansible"
  value       = random_password.app.result
  sensitive   = true
}
