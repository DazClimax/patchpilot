# Changelog

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
