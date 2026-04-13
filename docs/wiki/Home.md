# PatchPilot Wiki

Welcome to the PatchPilot wiki.

PatchPilot is a lightweight, self-hosted patch management system for Linux nodes with a pull-based agent model. Agents always initiate the connection to the server, so you do not need SSH fan-out or inbound access to managed guests.

## Quick links

- [Installation](Installation)
- [Agent Deployment](Agent-Deployment)
- [Troubleshooting](Troubleshooting)

## What PatchPilot is good at

- Self-hosted patch management for Debian, Ubuntu, and current RPM-capable clients
- Pull-based agents behind NAT
- Patch jobs, reboot jobs, schedules, and fleet visibility
- Ping-only monitoring for routers and other non-agent systems
- Low operational footprint with SQLite, systemd, and a stdlib-only Python agent

## Fastest server install

```bash
curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/v1.7.2/setup.sh | sudo bash
```

After the install finishes:

1. Open the web UI on `https://<server-ip>:8443`
2. Retrieve the bootstrap password from `/opt/patchpilot/bootstrap-admin.txt` if you did not predefine `PATCHPILOT_ADMIN_PASSWORD`
3. Open the **Deploy** page to generate the secure installer for your first agent

## Notes

- The bare metal installer targets Debian/Ubuntu-style hosts
- Docker is supported for the server
- Home Assistant OS uses the dedicated add-on flow
