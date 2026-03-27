# PatchPilot HAOS Agent

This add-on connects Home Assistant OS to PatchPilot.

## Options

Home Assistant renders these fields as a normal add-on form in the UI.

- `patchpilot_server`: URL to the PatchPilot agent port, for example `https://192.168.111.20:8050`
- `register_key`: register key from the PatchPilot deploy page
- `agent_id`: optional name for this Home Assistant instance
- `poll_interval`: polling interval in seconds
- `ca_pem`: optional PEM content for self-signed TLS certificates

## First Version

Supports:

- `HA Backup`
- `HA Core Update`
- `HA Backup + Update`

Shows an available Core update as a pending update in PatchPilot.
