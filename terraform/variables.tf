variable "prefix" {
  description = "Префикс имён сетей, томов и контейнеров стенда"
  type        = string
  default     = "stand"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.prefix))
    error_message = "Префикс: строчные латинские буквы, цифры и дефис, до 16 символов."
  }
}

variable "edge_bind" {
  description = "Адрес хоста, на котором открыт стенд. 127.0.0.1 — только с этой машины"
  type        = string
  default     = "127.0.0.1"
}

variable "edge_port" {
  description = "Порт хоста для nginx — единственный открытый порт стенда"
  type        = number
  default     = 8080
}

variable "subnets" {
  description = "Подсети трёх сегментов: edge — вход, app — сервис, db — базы"
  type        = map(string)
  default = {
    edge = "172.30.1.0/24"
    app  = "172.30.2.0/24"
    db   = "172.30.3.0/24"
  }
}

variable "postgres_image" {
  description = "Образ PostgreSQL; для воспроизводимости — с digest"
  type        = string
  default     = "postgres:16-alpine"
}

variable "nginx_image" {
  description = "nginx без root: процесс в контейнере не может стать root на хосте через уязвимость"
  type        = string
  default     = "nginxinc/nginx-unprivileged:1.28-alpine"
}
