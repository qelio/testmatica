data "yandex_compute_image" "ubuntu" {
  family = "ubuntu-2404-lts"
}

resource "yandex_compute_instance" "app" {
  name                      = "testmatica-app"
  hostname                  = "testmatica-app"
  platform_id               = "standard-v3"
  zone                      = var.zone
  service_account_id        = yandex_iam_service_account.vm.id
  allow_stopping_for_update = true

  resources {
    cores         = var.vm_cores
    memory        = var.vm_memory_gb
    core_fraction = 100
  }

  boot_disk {
    initialize_params {
      image_id = data.yandex_compute_image.ubuntu.id
      type     = "network-ssd"
      size     = var.vm_disk_gb
    }
  }

  network_interface {
    subnet_id          = yandex_vpc_subnet.main.id
    nat                = true
    nat_ip_address     = yandex_vpc_address.app.external_ipv4_address[0].address
    security_group_ids = [yandex_vpc_security_group.app.id]
  }

  metadata = {
    user-data = templatefile("${path.module}/cloud-init.yaml", {
      user    = var.vm_user
      ssh_key = var.ssh_public_key
    })
  }

  # Образ ОС обновляется в облаке регулярно — не пересоздаём ВМ из-за этого.
  lifecycle {
    ignore_changes = [boot_disk[0].initialize_params[0].image_id, metadata]
  }
}
