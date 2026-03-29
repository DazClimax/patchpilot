# PatchPilot HAOS Agent

This add-on connects Home Assistant OS to PatchPilot.

## Installation

1. Open the Home Assistant Add-on Store.
2. Add the PatchPilot GitHub repository.
3. Install `PatchPilot HAOS Agent`.
4. Open the add-on configuration.
5. Paste your PatchPilot values.
6. Start or restart the add-on.
7. Wait about 30 seconds and check PatchPilot.

## Required Options

Home Assistant renders these fields as a normal add-on form in the UI.

- `patchpilot_server`: URL to the PatchPilot agent port, for example `https://192.168.111.20:8050`
- `register_key`: register key from the PatchPilot deploy page
- `agent_id`: optional name for this Home Assistant instance
- `advertise_ip`: optional fixed LAN IP, for example `192.168.111.12`, if Home Assistant reports a Docker/internal address
- `poll_interval`: polling interval in seconds
- `ca_pem`: optional PEM content for self-signed TLS certificates

Example add-on configuration:

```yaml
patchpilot_server: "https://192.168.111.20:8050"
register_key: "PASTE_YOUR_REGISTER_KEY_HERE"
agent_id: "homeassistant"
advertise_ip: "192.168.111.12"
poll_interval: 30
ca_pem: |
  -----BEGIN CERTIFICATE-----
  ...
  -----END CERTIFICATE-----
```

## Optional Option

- `agent_update_webhook_id`: optional Home Assistant webhook ID for automatic PatchPilot add-on updates

## First Version

Supports:

- `HA Backup`
- `HA Core Update`
- `HA Backup + Update`
- `HA Supervisor Update`
- `HA OS Update`
- `HA Add-on Update`
- `HA Add-ons Update`

Shows available Core, Supervisor, OS, and Add-on updates as pending updates in PatchPilot.

## Updating The PatchPilot Add-on

PatchPilot can show when the HAOS add-on itself has an update available, but the add-on must be updated from the Home Assistant Add-on Store. It is intentionally skipped by the `HA Add-ons` batch action inside PatchPilot.

## Optional Auto-Update Trigger

This is optional. The add-on works normally without it.

If you want PatchPilot to trigger Home Assistant to update the PatchPilot HAOS add-on, do this:

1. Create the automation below in Home Assistant.
2. Pick a webhook ID, for example `patchpilot-ha-agent-update`.
3. Put that same value into the add-on option `agent_update_webhook_id`.
4. Save and restart the add-on.
5. PatchPilot can then trigger the HA add-on update flow for this agent.

```yaml
automation:
  - alias: PatchPilot HAOS Agent Auto Update
    trigger:
      - platform: webhook
        webhook_id: patchpilot-ha-agent-update
    action:
      - service: update.install
        target:
          entity_id: update.patchpilot_haos_agent_update
```

If your update entity has a different name, search for `patchpilot` in Home Assistant entities and replace the entity ID accordingly.
