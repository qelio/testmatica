resource "yandex_vpc_network" "main" {
  name = "testmatica"
}

resource "yandex_vpc_subnet" "main" {
  name           = "testmatica-${var.zone}"
  zone           = var.zone
  network_id     = yandex_vpc_network.main.id
  v4_cidr_blocks = ["10.10.0.0/24"]
}

# Постоянный публичный адрес ВМ — на него смотрят DNS-записи.
resource "yandex_vpc_address" "app" {
  name = "testmatica-app"
  external_ipv4_address {
    zone_id = var.zone
  }
}

# ВМ: снаружи — только сайт (80/443), SSH и медиа видеосвязи.
resource "yandex_vpc_security_group" "app" {
  name       = "testmatica-app"
  network_id = yandex_vpc_network.main.id

  ingress {
    description    = "SSH"
    protocol       = "TCP"
    port           = 22
    v4_cidr_blocks = var.ssh_allowed_cidrs
  }
  ingress {
    description    = "HTTP (выдача сертификатов и переадресация на HTTPS)"
    protocol       = "TCP"
    port           = 80
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description    = "HTTPS"
    protocol       = "TCP"
    port           = 443
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description    = "LiveKit: медиа по TCP"
    protocol       = "TCP"
    port           = 7881
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description    = "LiveKit: медиа по UDP"
    protocol       = "UDP"
    port           = 7882
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description    = "LiveKit: TURN"
    protocol       = "UDP"
    port           = 3478
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description    = "LiveKit: ретрансляция TURN"
    protocol       = "UDP"
    from_port      = 30000
    to_port        = 30100
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    description    = "Исходящие — любые"
    protocol       = "ANY"
    from_port      = 0
    to_port        = 65535
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}
