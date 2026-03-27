# PatchPilot HAOS Agent

First Home Assistant OS integration for PatchPilot.

This add-on:

- registers a Home Assistant OS instance as its own PatchPilot agent
- reports an available Core update as a pending update
- supports the job types `ha_backup`, `ha_core_update`, and `ha_backup_update`

## Configuration

- `patchpilot_server`: URL to the PatchPilot agent port
- `register_key`: current register key from PatchPilot
- `agent_id`: optional fixed name
- `poll_interval`: polling interval in seconds
- `ca_pem`: optional PEM content for self-signed TLS servers

## Status

This is the first implementation stage. Supervisor and OS updates will follow later.
