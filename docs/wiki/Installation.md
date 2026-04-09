# Installation

This page covers the quickest supported way to get a PatchPilot server running.

## Bare metal server install

Recommended for Debian and Ubuntu hosts:

```bash
curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/v1.6.5/setup.sh | sudo bash
```

With custom ports:

```bash
curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/v1.6.5/setup.sh | sudo PORT=443 AGENT_PORT=8050 bash
```

If you want to inspect the script first:

```bash
curl -fsSL https://raw.githubusercontent.com/DazClimax/patchpilot/v1.6.5/setup.sh -o setup.sh
less setup.sh
sudo bash setup.sh
```

## What the installer does

The installer will:

- install required system dependencies with `apt`
- install Node.js 20 if it is needed for the frontend build
- build the frontend locally
- install PatchPilot under `/opt/patchpilot`
- create the Python virtual environment under `/opt/patchpilot-venv`
- generate a self-signed certificate
- register and start the systemd service

## First login

If you did not predefine `PATCHPILOT_ADMIN_PASSWORD`, read the generated bootstrap password:

```bash
sudo cat /opt/patchpilot/bootstrap-admin.txt
```

Then open:

```text
https://<server-ip>:8443
```

Your browser warning is expected on first access when using the generated self-signed certificate.

## Docker option

PatchPilot also supports a Docker server deployment. See the main README for the current container instructions and image reference.

## Next step

Continue with [Agent Deployment](Agent-Deployment) after the server is reachable.
