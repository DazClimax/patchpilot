# Agent Deployment

PatchPilot uses a pull-based agent model. The server never connects to the VM directly. Each agent initiates registration, heartbeat, and job polling on its own.

## Recommended deployment path

The recommended way to deploy an agent is through the **Deploy** page in the PatchPilot web UI.

1. Sign in to the PatchPilot dashboard
2. Open the **Deploy** page
3. Generate a registration key
4. Copy the generated secure installer
5. Run it on the target machine

Example:

```bash
printf '%s' '<DEPLOY_PAGE_BASE64_INSTALLER>' | base64 -d | sudo bash
```

## Why this is the preferred path

The Deploy page installer embeds:

- the current registration key
- the correct server URL
- and, for HTTPS deployments, the CA certificate required to validate later downloads

That avoids insecure bootstrap patterns such as `curl -k | bash`.

## What the agent does after install

On first start, the agent:

1. registers with `POST /api/agents/register`
2. stores `agent_id` and `token` in `/etc/patchpilot/state.json`
3. sends heartbeats on the configured interval
4. polls for pending jobs
5. reports job results back to the server

## Agent files

- `/etc/patchpilot/agent.conf` — agent configuration
- `/etc/patchpilot/state.json` — persisted agent identity and token
- `/etc/patchpilot/ca.pem` — CA certificate for HTTPS trust when needed
- `/opt/patchpilot/agent/agent.py` — agent runtime

## Useful verification

Check the service:

```bash
systemctl status patchpilot-agent
```

Follow logs:

```bash
journalctl -u patchpilot-agent -f
```

If the registration succeeds, the agent should appear on the dashboard shortly afterward.
