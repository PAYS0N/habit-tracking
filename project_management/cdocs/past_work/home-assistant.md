# Home Assistant — Context Document

## Deployment

Home Assistant runs as a Docker container (`homeassistant`) on the Pi using the official image `ghcr.io/home-assistant/home-assistant:stable`. It is on Docker bridge network `ha_network` (`172.19.0.0/16`) at static IP `172.19.0.10`. Ports 8123 (web UI / API) and 6053 (ESPHome) are published to the host. The HA config directory is mounted at `/home/pays0n/homeassistant`. The container has access to `/dev/ttyUSB0` for serial devices.

HA is reachable on the LAN at `http://192.168.22.1:8123` (via NAT from the Pi's wlan0 IP) or directly at `http://172.19.0.10:8123` from within the Docker network. The iptables INPUT chain explicitly permits port 8123 from wlan0, and a DNAT rule forwards external port-8123 traffic to `172.18.0.2:8123` (note: NAT rules reference `172.18.0.2` which may reflect an older bridge assignment).

## Bermuda BLE Room Tracking

Bermuda is installed as a Home Assistant custom integration. It uses Bluetooth Low Energy RSSI from fixed ESP32-S3 proxy devices to determine the room location of tracked BLE devices. Three ESP32-S3 devices act as proxies at `192.168.22.10–.12` (hostnames: bermuda-proxy-01/02/03), placed in different rooms. Each proxy reports BLE advertisement signal strength back to HA via ESPHome.

Bermuda exposes room location as HA sensor entities. The entity naming convention follows the pattern `sensor.<device_name>_ble_room` (exact entity IDs must be verified in HA → Developer Tools → States). Currently tracked devices: `payson_s25` (`sensor.payson_s25_ble_room`), `iphone_14` (`sensor.iphone_14_ble_room`). Other devices (laptops) are not BLE-tracked and will return `unknown` room context.

The state value of a room entity is a string matching the area name configured in HA (e.g., `"bedroom"`, `"living_room"`, `"office"`). States `"unknown"` and `"unavailable"` are treated as no data. Room names in HA must be consistent with the `relax_rooms` list in the Productivity Guard config.

## REST API

HA exposes a REST API at `/api/`. Authentication requires a long-lived access token passed as `Authorization: Bearer <token>`. The token is stored in `backend/config.yaml` (gitignored) or injected via the `HA_TOKEN` environment variable. The Productivity Guard backend queries `GET /api/states/<entity_id>` to retrieve device room data; the response JSON contains `"state"` as the current value.

## Automations (Productivity Guard Integration)

Two automations in `homeassistant/automations.yaml` integrate with the Productivity Guard backend via REST commands. When `sensor.payson_s25_ble_room` transitions to `"bedroom"`, the automation calls `rest_command.productivity_guard_force_block` with `device_ip: "192.168.22.75"`, which POSTs to `http://192.168.22.1:8800/force-block`. When the phone leaves `"bedroom"` (state transitions from `"bedroom"`), the automation calls `productivity_guard_force_unblock` to the `/force-unblock` endpoint.

REST commands are defined in `homeassistant/rest_commands.yaml` and must be included in `configuration.yaml` under `rest_command:`. Three commands exist: `productivity_guard_force_block`, `productivity_guard_force_unblock`, and `productivity_guard_revoke_all` (for a panic-button time trigger, currently commented out in automations).

## DNS Resolution

The Pi's dnsmasq serves DNS to all LAN clients including the HA container (via the Docker bridge). HA DNS queries from within the Docker network (`172.30.0.0/24` per iptables rules) are permitted to reach `192.168.22.1:53`. HA can resolve local hostnames and blocked domains will return `0.0.0.0` for HA as well, though HA itself is not a target of the Productivity Guard blocking.

## ESPHome

Port 6053 is published for the ESPHome integration, which manages the ESP32-S3 BLE proxy devices. The ESP32s are assigned static IPs at `.10–.12` by dnsmasq and communicate with HA via the ESPHome native API on port 6053.
