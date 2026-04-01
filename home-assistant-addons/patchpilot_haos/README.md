# PatchPilot HAOS Agent

Dedicated Home Assistant OS integration for PatchPilot.

This add-on:

- registers a Home Assistant OS instance as its own PatchPilot agent
- reports available Core, Supervisor, OS, and Add-on updates as pending updates
- supports the job types `ha_backup`, `ha_core_update`, `ha_backup_update`, `ha_supervisor_update`, `ha_os_update`, `ha_addon_update`, and `ha_addons_update`

## Installation

1. Open the Home Assistant Add-on Store.
2. Add the PatchPilot GitHub repository.
3. Install `PatchPilot HAOS Agent`.
4. Open the add-on configuration.
5. Fill in the required PatchPilot connection values.
6. Start or restart the add-on.
7. Wait about 30 seconds for Home Assistant to appear in PatchPilot.

## Required Configuration

Use these values in the add-on form:

- `patchpilot_server`: URL to the PatchPilot agent port
- `register_key`: current register key from PatchPilot
- `agent_id`: optional fixed name
- `advertise_ip`: optional fixed LAN IP override if Home Assistant reports the wrong address
- `poll_interval`: polling interval in seconds
- `ca_pem`: optional PEM content for self-signed TLS servers
- `ca_rollover_pub_pem`: optional PatchPilot rollover public key for signed CA rotations

Example:

```yaml
patchpilot_server: "https://PATCHPILOT_HOST:8050"
register_key: "PASTE_YOUR_REGISTER_KEY_HERE"
agent_id: "homeassistant"
advertise_ip: "YOUR_HOME_ASSISTANT_LAN_IP"
poll_interval: 30
ca_pem: |
  -----BEGIN CERTIFICATE-----
  ...
  -----END CERTIFICATE-----
ca_rollover_pub_pem: |
  -----BEGIN PUBLIC KEY-----
  ...
  -----END PUBLIC KEY-----
```

## Optional Configuration

- `agent_update_webhook_id`: optional Home Assistant webhook ID for automatic PatchPilot add-on updates

If you do not set `agent_update_webhook_id`, everything still works normally. You will just continue to update the PatchPilot HAOS add-on manually from Home Assistant.

## Status

Home Assistant OS is the supported scope for this add-on. Deprecated installation methods are intentionally not covered here.
Update the PatchPilot HAOS add-on itself through the Home Assistant Add-on Store, not through the `HA Add-ons` action in PatchPilot.

## Optional: Automatic Add-on Update Trigger

PatchPilot works without this. If you want PatchPilot to trigger HAOS agent updates for you, do this:

1. Create the Home Assistant automation below.
2. Choose a webhook ID, for example `patchpilot-ha-agent-update`.
   Use a hard-to-guess value if Home Assistant is reachable from anything other than your private LAN.
3. Put the same webhook ID into the add-on option `agent_update_webhook_id`.
4. Save and restart the add-on.
5. PatchPilot will then show the HA agent as auto-update capable.

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
    mode: single
```

The update entity name can vary slightly. If needed, search Home Assistant entities for `patchpilot` and replace `update.patchpilot_haos_agent_update` with the entity shown on your system.

Add this to the PatchPilot HAOS add-on configuration as well:

```yaml
agent_update_webhook_id: "patchpilot-ha-agent-update"
```

Accepted format: 8 to 128 characters using only letters, numbers, `-`, or `_`.
