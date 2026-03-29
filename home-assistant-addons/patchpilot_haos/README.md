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
- `agent_update_webhook_id`: optional Home Assistant webhook ID for automatic PatchPilot add-on updates
- `poll_interval`: polling interval in seconds
- `ca_pem`: optional PEM content for self-signed TLS servers

## Status

Home Assistant OS is the supported scope for this add-on. Deprecated installation methods are intentionally not covered here.
Update the PatchPilot HAOS add-on itself through the Home Assistant Add-on Store, not through the `HA Add-ons` action in PatchPilot.

## Optional: Automatic Add-on Update Trigger

PatchPilot works without this. If you want PatchPilot to trigger HAOS agent updates for you, create a Home Assistant automation that installs the PatchPilot add-on update when a webhook is called, and then enter the same webhook ID in the add-on option `agent_update_webhook_id`.

Example automation:

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

The update entity name can vary slightly. If needed, search Home Assistant entities for `patchpilot` and replace `update.patchpilot_haos_agent_update` with the entity shown on your system.
