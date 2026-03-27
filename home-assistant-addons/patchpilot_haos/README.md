# PatchPilot HAOS Agent

Erste Home-Assistant-OS-Integration fuer PatchPilot.

Dieses Add-on:

- registriert eine Home Assistant OS Instanz als eigenen PatchPilot-Agent
- meldet ein verfuegbares Core-Update als Pending Update
- unterstuetzt die Jobtypen `ha_backup`, `ha_core_update` und `ha_backup_update`

## Konfiguration

- `patchpilot_server`: URL zum PatchPilot-Agent-Port
- `register_key`: aktueller Register-Key aus PatchPilot
- `agent_id`: optionaler fester Name
- `poll_interval`: Poll-Intervall in Sekunden
- `ca_pem`: optionaler PEM-Inhalt fuer selbstsignierte TLS-Server

## Status

Dies ist die erste Implementierungsstufe. Supervisor- und OS-Updates folgen spaeter.
