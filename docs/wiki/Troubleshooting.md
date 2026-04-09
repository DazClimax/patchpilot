# Troubleshooting

This page collects a few common issues that come up during first setup.

## Server will not start

Check the recent service logs:

```bash
journalctl -u patchpilot -n 50 --no-pager
```

Common causes:

- port already in use
- missing dependencies
- wrong ownership below `/opt/patchpilot`
- missing SSL certificate files

Useful checks:

```bash
sudo ss -tlnp | grep 8443
sudo chown -R patchpilot:patchpilot /opt/patchpilot/
```

## Agent does not appear on the dashboard

Start with the agent logs:

```bash
journalctl -u patchpilot-agent -n 30 --no-pager
```

Common causes:

- wrong server URL in `/etc/patchpilot/agent.conf`
- expired registration key
- firewall blocking the connection
- CA trust missing for a self-signed HTTPS deployment

Useful check:

```bash
curl --cacert /etc/patchpilot/ca.pem https://<server-ip>:<agent-port>/api/ping
```

## Agent gets a new ID after every restart

This usually means `/etc/patchpilot/state.json` is missing or has the wrong permissions.

Check:

```bash
ls -la /etc/patchpilot/state.json
```

Expected:

- file exists
- owned by `root`
- mode `600`

## Browser says "Authentication required"

Sign in with your username and password. If you still rely on the legacy admin key, retrieve or define it in the server environment and restart the service.

```bash
journalctl -u patchpilot | grep "ephemeral key"
```
