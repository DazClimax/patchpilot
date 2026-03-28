# Home Assistant OS Add-on

PatchPilot supports Home Assistant OS through a dedicated add-on.

This is separate from the regular Linux server installer. The current RPM/Fedora work applies to managed client systems and agents, while Home Assistant OS is handled through this dedicated add-on path.

## What It Supports

- register Home Assistant OS as a `haos` agent in PatchPilot
- show available Core, Supervisor, OS, and Add-on updates as pending updates
- run the following jobs from PatchPilot:
  - `HA Backup`
  - `HA Core Update`
  - `HA Backup + Update`
  - `HA Supervisor Update`
  - `HA OS Update`
  - `HA Add-on Update`
  - `HA Add-ons Update`

## Add-on Repository

The add-on lives in this repository under:

- `home-assistant-addons/repository.yaml`
- `home-assistant-addons/patchpilot_haos/`

## Installation in Home Assistant

1. Open `Repositories` in the Add-on Store.
2. Add the PatchPilot GitHub repository as an add-on repository.
3. Install `PatchPilot HAOS Agent`.
4. Set the options:
   - `patchpilot_server`
   - `register_key`
   - optional `agent_id`
   - optional `advertise_ip`
   - optional `ca_pem`
5. Start the add-on.
6. Update the PatchPilot HAOS add-on itself through the Home Assistant Add-on Store, not through `HA Add-ons` inside PatchPilot.

## Notes

- `ha_backup_update` uses the official Supervisor API with `backup=true`.
- The supported scope is Home Assistant OS.
- Deprecated Home Assistant installation methods are intentionally not covered.
