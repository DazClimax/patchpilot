# Home Assistant OS Add-on

The first PatchPilot path for Home Assistant OS runs as a dedicated add-on.

## What This First Version Can Do

- register Home Assistant OS as a `haos` agent in PatchPilot
- show an available Core update as a pending update
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
   - optional `ca_pem`
5. Start the add-on.

## Notes

- `ha_backup_update` uses the official Supervisor API with `backup=true`.
- The supported scope is Home Assistant OS.
- Deprecated Home Assistant installation methods are intentionally not covered.
