# Changelog

## 0.2.21

- Added a persistent HA add-on update callback so PatchPilot can confirm the new agent version after Home Assistant restarts the add-on.
- Improved deployment feedback handling for the HAOS agent and bumped the reported PatchPilot agent version to `1.7`.

## 0.2.20

- Added detection of Home Assistant `update.*` entities so HACS and frontend-style updates such as custom cards can appear in PatchPilot.
- Bumped the HAOS-reported PatchPilot agent version to `1.6`.

## 0.2.18

- Enlarged the visible PatchPilot logo inside the Home Assistant add-on icon and logo assets so it appears bigger in the Add-on Store.

## 0.2.17

- Bumped the HAOS-reported PatchPilot agent version to `1.4` for another webhook auto-update test.

## 0.2.16

- Fixed PatchPilot batch-status reporting so optional HA agent auto-updates appear correctly in the deployment modal.
- Hardened optional `agent_update_webhook_id` handling by accepting only safe webhook ID characters.
- Bumped the HAOS-reported PatchPilot agent version to `1.3` for another end-to-end auto-update test.

## 0.2.15

- Bumped the HAOS-reported PatchPilot agent version to `1.2` for end-to-end testing of the optional webhook-based auto-update flow.

## 0.2.14

- Improved the HAOS add-on documentation with a step-by-step install guide.
- Added ready-to-copy example YAML for both the normal add-on config and the optional webhook automation.

## 0.2.13

- Test release to verify the optional Home Assistant webhook-based PatchPilot add-on update flow.

## 0.2.12

- Added optional `agent_update_webhook_id` support so PatchPilot can trigger a Home Assistant automation for HAOS add-on updates.
- Report a dedicated HA auto-update capability back to PatchPilot when that webhook option is configured.

## 0.2.11

- Bumped the PatchPilot agent version reported by the Home Assistant OS add-on to `1.1`.

## 0.2.10

- Added `agent_version` reporting for the Home Assistant OS agent so it appears in the new PatchPilot agent-version overview.
- Return a clear message when a generic `update_agent` job is sent to HAOS, instead of failing with `Unknown job type`.

## 0.2.9

- Fixed HAOS LAN IP detection for Supervisor network data where `ipv4.address` is returned as a list.

## 0.2.8

- Excluded Docker, bridge, and other virtual interfaces from HAOS LAN IP detection.
- Prefer the primary non-virtual Home Assistant network interface before any fallback candidate.

## 0.2.7

- Refreshed add-on branding assets to force Home Assistant to reload the new PatchPilot icon and logo.

## 0.2.6

- Made HAOS uptime detection robust across second, millisecond, microsecond, and nanosecond boot timestamp formats.
- Prefer the primary Home Assistant network interface even more aggressively when detecting the reported LAN IP.

## 0.2.5

- Prefer the primary Home Assistant network interface when auto-detecting the LAN IP.
- Show PatchPilot HAOS add-on updates again as a visible pending item, without trying to self-update through `HA Add-ons`.

## 0.2.4

- Switched HAOS IP discovery to also read Supervisor `/network/info` interface data.
- Added support for nested Supervisor IPv4 fields like `ipv4.ip_address`.
- Improved HAOS uptime reporting using the official host boot timestamp when available.

## 0.2.3

- Improved Home Assistant OS IP detection to handle additional Supervisor interface formats.
- Added uptime reporting for the HAOS agent.

## 0.2.2

- Excluded the PatchPilot HAOS add-on from add-on update detection.
- Prevented `HA Add-ons` and single add-on updates from trying to update the running PatchPilot add-on itself.

## 0.2.1

- Added `advertise_ip` to override the IP address reported to PatchPilot.
- Improved LAN IP detection to prefer real private network addresses over container/internal addresses.
- Added PatchPilot deploy-page support for generating ready-to-paste Home Assistant add-on config with `advertise_ip`.

## 0.2.0

- Added Home Assistant Supervisor update support.
- Added Home Assistant OS update support.
- Added single add-on update support.
- Added update-all add-ons support.
- Expanded pending update reporting for Core, Supervisor, OS, and installed add-ons.

## 0.1.1

- Fixed Home Assistant IP reporting to prefer a real local IPv4 address.
- Added Home Assistant add-on branding assets.

## 0.1.0

- Initial Home Assistant OS add-on release.
- Added agent registration with PatchPilot.
- Added Home Assistant backup support.
- Added Home Assistant Core update support.
- Added backup plus Core update support.
