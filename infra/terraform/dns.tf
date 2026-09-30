# DNS-зона в Yandex Cloud DNS. У регистратора домена нужно указать NS: ns1.yandexcloud.net, ns2.yandexcloud.net.
# Записи для почты (Postbox: DKIM, SPF) добавляются после подтверждения домена в Postbox — см. docs/deploy.md.

resource "yandex_dns_zone" "main" {
  count  = var.manage_dns ? 1 : 0
  name   = "testmatica"
  zone   = "${var.domain}."
  public = true
}

resource "yandex_dns_recordset" "apex" {
  count   = var.manage_dns ? 1 : 0
  zone_id = yandex_dns_zone.main[0].id
  name    = "${var.domain}."
  type    = "A"
  ttl     = 300
  data    = [yandex_vpc_address.app.external_ipv4_address[0].address]
}

resource "yandex_dns_recordset" "www" {
  count   = var.manage_dns ? 1 : 0
  zone_id = yandex_dns_zone.main[0].id
  name    = "www.${var.domain}."
  type    = "A"
  ttl     = 300
  data    = [yandex_vpc_address.app.external_ipv4_address[0].address]
}

resource "yandex_dns_recordset" "livekit" {
  count   = var.manage_dns ? 1 : 0
  zone_id = yandex_dns_zone.main[0].id
  name    = "${var.livekit_subdomain}.${var.domain}."
  type    = "A"
  ttl     = 300
  data    = [yandex_vpc_address.app.external_ipv4_address[0].address]
}
