# Home Assistant OS Add-on

Der erste PatchPilot-Pfad fuer Home Assistant OS laeuft als eigenes Add-on.

## Was diese erste Version kann

- Home Assistant OS als `haos`-Agent bei PatchPilot registrieren
- ein verfuegbares Core-Update als Pending Update anzeigen
- folgende Jobs aus PatchPilot ausfuehren:
  - `HA Backup`
  - `HA Core Update`
  - `HA Backup + Update`

## Add-on Repository

Im Repo liegt das Add-on unter:

- `home-assistant-addons/repository.yaml`
- `home-assistant-addons/patchpilot_haos/`

## Installation in Home Assistant

1. Im Add-on Store `Repositories` oeffnen.
2. Das PatchPilot-GitHub-Repo als Add-on-Repository hinzufuegen.
3. `PatchPilot HAOS Agent` installieren.
4. Optionen setzen:
   - `patchpilot_server`
   - `register_key`
   - optional `agent_id`
   - optional `ca_pem`
5. Add-on starten.

## Hinweise

- Fuer `ha_backup_update` wird die offizielle Supervisor-API mit `backup=true` genutzt.
- Diese erste Version deckt nur Home Assistant Core auf HA OS ab.
- Supervisor-, OS- und Add-on-Updates folgen spaeter.
