# PatchPilot HAOS Agent

Dedicated Home Assistant OS integration for PatchPilot.

This add-on:

- registers a Home Assistant OS instance as its own PatchPilot agent
- reports available Core, Supervisor, OS, and Add-on updates as pending updates
- supports the job types `ha_backup`, `ha_core_update`, `ha_backup_update`, `ha_supervisor_update`, `ha_os_update`, `ha_addon_update`, and `ha_addons_update`

## Configuration

- `patchpilot_server`: URL to the PatchPilot agent port
- `register_key`: current register key from PatchPilot
- `agent_id`: optional fixed name
- `advertise_ip`: optional fixed LAN IP override if Home Assistant reports the wrong address
- `poll_interval`: polling interval in seconds
- `ca_pem`: optional PEM content for self-signed TLS servers

## Status

Home Assistant OS is the supported scope for this add-on. Deprecated installation methods are intentionally not covered here.
Update the PatchPilot HAOS add-on itself through the Home Assistant Add-on Store, not through the `HA Add-ons` action in PatchPilot.
