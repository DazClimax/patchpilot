# PatchPilot HAOS Agent

Dieses Add-on verbindet Home Assistant OS mit PatchPilot.

## Optionen

- `patchpilot_server`: URL zum PatchPilot-Agent-Port, z. B. `https://192.168.111.20:8050`
- `register_key`: Register-Key aus der PatchPilot-Deploy-Seite
- `agent_id`: optionaler Name fuer diese Home-Assistant-Instanz
- `poll_interval`: Poll-Intervall in Sekunden
- `ca_pem`: optionaler PEM-Inhalt fuer selbstsignierte TLS-Zertifikate

## Erste Version

Unterstuetzt:

- `HA Backup`
- `HA Core Update`
- `HA Backup + Update`

Zeigt ein verfuegbares Core-Update als Pending Update in PatchPilot an.
