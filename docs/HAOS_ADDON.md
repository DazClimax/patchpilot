# Home Assistant OS Add-on

PatchPilot supports Home Assistant OS through a dedicated add-on.

This is separate from the regular Linux server installer. The current RPM/Fedora work applies to managed client systems and agents, while Home Assistant OS is handled through this dedicated add-on path.

## What It Supports

- register Home Assistant OS as a `haos` agent in PatchPilot
- show available Core, Supervisor, OS, and Add-on updates as pending updates
- show Home Assistant `update.*` entities such as HACS/frontend updates as pending updates
- run the following jobs from PatchPilot:
  - `HA Backup`
  - `HA Core Update`
  - `HA Backup + Update`
  - `HA Supervisor Update`
  - `HA OS Update`
  - `HA Add-on Update`
  - `HA Add-ons Update`
  - targeted `update.*` entity installs

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
   - optional `agent_update_webhook_id`
   - optional `ca_pem`
5. Start the add-on.
6. If you keep `agent_update_webhook_id` empty, update the PatchPilot HAOS add-on manually through the Home Assistant Add-on Store. If you configure the webhook flow below, PatchPilot can trigger that update for you.

Example add-on configuration:

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
```

## Notes

- `ha_backup_update` uses the official Supervisor API with `backup=true`.
- The supported scope is Home Assistant OS.
- Deprecated Home Assistant installation methods are intentionally not covered.

## Optional Auto-Update From PatchPilot

This is optional. Without it, the add-on still works normally and PatchPilot will simply continue to show HA add-on updates as manual Home Assistant updates.

If you want PatchPilot to trigger the HA add-on update flow for this Home Assistant instance:

1. Create the Home Assistant automation below.
2. Pick a webhook ID, for example `patchpilot-ha-agent-update`.
3. Put the same value into the add-on option `agent_update_webhook_id`.
4. Save and restart the add-on.
5. PatchPilot can then include this HA instance in normal `Update Agents` runs.

## Signed Trust Rotation

For HTTPS certificate changes, include both of these values in the add-on config:

- `ca_pem`
- `ca_rollover_pub_pem`

PatchPilot uses them to deliver signed CA rollover payloads during **Deploy Trust to Agents**. If the HAOS add-on is online during that rollout, it can accept the new trust bundle automatically before the server certificate is switched.

Automation example:

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

Add this to the add-on configuration as well:

```yaml
agent_update_webhook_id: "patchpilot-ha-agent-update"
```

Notes:

- If the update entity has a different name on your system, search for `patchpilot` in Home Assistant entities and replace `update.patchpilot_haos_agent_update`.
- Use a hard-to-guess webhook ID if Home Assistant is reachable from anything other than your private LAN.
- Accepted webhook format: 8 to 128 characters using only letters, numbers, `-`, or `_`.
