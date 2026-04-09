# Raspberry Pi Router — Context Document

## Hardware Role

The Pi (hostname: kuudra) is the network router for the home WiFi. It has two network interfaces: `eth0` (upstream internet, WAN) and `wlan0` (access point, LAN). All WiFi clients route through it; it is the default gateway at `192.168.22.1`.

## Access Point

hostapd runs on `wlan0`, broadcasting SSID "Payson" on channel 6 (2.4 GHz, 802.11g/n, WPA2-PSK). AP isolation is disabled, so clients can communicate with each other. Config is at `/etc/hostapd/hostapd.conf`.

## DNS and DHCP

dnsmasq serves DNS and DHCP on `wlan0`, bound exclusively to `192.168.22.1`. DHCP dynamic range is `.100–.200` with 12-hour leases. Static leases are configured by MAC address in `/etc/dnsmasq.d/router.conf`. Address scheme: Pi at `.1`; ESP32-S3 BLE proxies at `.10–.19`; laptops/PCs at `.50–.74`; phones/tablets at `.75–.99`.

Known static assignments: voidgloom `.50`, plantera `.51`, akura_malice `.52`, coral `.53`, payson_s25 `.75`, iphone_14 `.76`, notebook `.77`, bermuda-proxy-01/02/03 at `.10/.11/.12`.

dnsmasq loads an additional hosts file at `/etc/productivity-guard/blocked_hosts` via `addn-hosts` directive. This file maps blocked domains to `0.0.0.0` and is reloaded live via SIGHUP (no restart required). `local-ttl=5` is set so blocked-domain responses expire quickly on clients. A separate static config at `/etc/dnsmasq.d/doh_block.conf` blocks all major DNS-over-HTTPS providers by hostname and uses the Firefox canary domain (`use-application-dns.net`) to auto-disable DoH in Firefox. dnsmasq leases are readable at `/var/lib/misc/dnsmasq.leases`.

## Firewall

iptables manages all packet filtering, saved via `iptables-persistent` (`netfilter-persistent save`) to `/etc/iptables/rules.v4`. Default INPUT policy is DROP; OUTPUT is ACCEPT; FORWARD is DROP except where explicitly permitted.

INPUT permits: loopback, established/related connections, SSH from `192.168.22.0/24` on wlan0, DNS (TCP+UDP/53) from the LAN to `.1`, mDNS (UDP/5353) to `224.0.0.251` from LAN, DHCP (UDP/67) on wlan0, ICMP echo, DNS from the HA Docker subnet (`172.30.0.0/24`) to `.1`, HTTP on port 8123 from wlan0 (Home Assistant), HTTP on port 8800 from wlan0 (Productivity Guard backend). Tailscale input is handled by the `ts-input` chain.

FORWARD permits: intra-wlan0 traffic, established/related, and outbound from wlan0 to eth0 only for IPs in the `allowed_internet` ipset. Docker traffic is managed by Docker-generated chains (`DOCKER-FORWARD`, `DOCKER-CT`, `DOCKER-BRIDGE`, `DOCKER-USER`). The `DOCKER-USER` chain drops traffic from `br+` interfaces to eth0 unless the source IP is in the `allowed_docker` ipset.

NAT POSTROUTING masquerades traffic from the `allowed_internet` ipset on eth0, and masquerades Docker subnets off their respective bridges. Port 8123 is DNAT'd from any external request to the HA container at `172.18.0.2:8123`.

## Internet Access Control (ipset)

Two ipsets are defined. `allowed_internet` (hash:ip) holds the IPs permitted to reach the internet; iptables FORWARD and POSTROUTING rules reference it. Currently contains: `.50, .51, .52, .53, .75, .76, .77`. `allowed_docker` (hash:ip) holds Docker container IPs permitted outbound access; currently empty at save time (HA at `172.19.0.10` is added transiently and must NOT be persisted). ipset config is saved to `/etc/ipset.conf`; to add/remove internet access: `sudo ipset add/del allowed_internet <ip>` then `sudo ipset save | sudo tee /etc/ipset.conf > /dev/null`.

## Docker

Rootful Docker runs Home Assistant as container `homeassistant` using image `ghcr.io/home-assistant/home-assistant:stable`. The container is on bridge network `ha_network` (`172.19.0.0/16`, gateway `172.19.0.1`) with static IP `172.19.0.10`. Ports 8123 and 6053 are published to the host. `/dev/ttyUSB0` is passed through. HA config lives at `/home/pays0n/homeassistant`. The container is managed via `docker compose` in `/home/pays0n/ha_docker/`. To restart: `sudo docker stop homeassistant && sudo docker rm homeassistant && sudo docker compose up -d`.

Note: The docker-compose network uses `172.19.0.0/16` but the iptables rules reference `172.18.0.0/16` and `172.30.0.0/24` for HA in some places — these reflect older or alternate bridge assignments and should be verified against `docker network ls` output.

## Tailscale

Tailscale is installed for remote access. The `ts-input` and `ts-forward` iptables chains handle Tailscale traffic. The Tailscale node IP is `100.68.1.124`. Tailscale CGNAT range is `100.64.0.0/10`; traffic from this range not on `tailscale0` is dropped.

## sudoers

The `pays0n` user has passwordless sudo for two commands: `tee /etc/productivity-guard/blocked_hosts` and `pkill -HUP dnsmasq`. This grants the Productivity Guard backend the minimum privilege needed to manage DNS blocking without broader root access.
