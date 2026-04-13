# Testing Notes

Stand: 2026-04-13
Branch: `codex/structure-split`

## Testumgebung

- PatchPilot-Testserver: `192.168.111.21`
- Frisch installierte Linux-Test-VM: `192.168.111.26`
  - Agent-ID: `Ubuntu`
- Frisch installierte Linux-Test-VM: `192.168.111.22`
  - Agent-ID: `Test2`

## Auf `.21` ausgerollter Stand

- aktueller Branch `codex/structure-split`
- Frontend neu gebaut
- Backend-Testlauf vor Deploy:
  - `python3 -m pytest server/tests -q`
  - Ergebnis: `94 passed`

## Echte Integrations-Tests

Die folgenden Flows wurden gegen die laufende Testinstanz auf `.21` und die frisch installierte VM `Ubuntu` auf `.26` real geprüft:

- Login
- Deploy / Register-Key
- Settings speichern
- Schedule erstellen und wieder löschen
- Einzelpaket-Update
- `Patch All`
- Agent-Detail `Refresh Updates`

Zusätzlich wurde auf der frisch installierten VM `Test2` auf `.22` real geprüft:

- frische Agent-Installation gegen `https://192.168.111.21:8050`
- Heartbeat und Paketinventar auf `.21`
- Einzelpaket-Update
- Agent-Detail `Refresh Updates`
- `Patch All`

## Aktuelle Playwright-Tests

Dateien:

- [`frontend/e2e/login.spec.ts`](/Users/jacques/Coding/patchpilot/frontend/e2e/login.spec.ts)
- [`frontend/e2e/settings.spec.ts`](/Users/jacques/Coding/patchpilot/frontend/e2e/settings.spec.ts)
- [`frontend/e2e/schedules.spec.ts`](/Users/jacques/Coding/patchpilot/frontend/e2e/schedules.spec.ts)
- [`frontend/e2e/ping-targets.spec.ts`](/Users/jacques/Coding/patchpilot/frontend/e2e/ping-targets.spec.ts)
- [`frontend/e2e/deploy.spec.ts`](/Users/jacques/Coding/patchpilot/frontend/e2e/deploy.spec.ts)
- [`frontend/e2e/agent-detail.spec.ts`](/Users/jacques/Coding/patchpilot/frontend/e2e/agent-detail.spec.ts)
- [`frontend/e2e/dashboard-actions.spec.ts`](/Users/jacques/Coding/patchpilot/frontend/e2e/dashboard-actions.spec.ts)

## Letzter echter E2E-Lauf

Kommando:

```bash
cd /Users/jacques/Coding/patchpilot/frontend
PP_E2E_BASE_URL='https://192.168.111.21:8443' \
PP_E2E_USERNAME='admin' \
PP_E2E_PASSWORD='duoTD0xNLpZIKvLd8DzyWA' \
PP_E2E_LINUX_AGENT_ID='Test2' \
npx playwright test \
  e2e/login.spec.ts \
  e2e/settings.spec.ts \
  e2e/schedules.spec.ts \
  e2e/ping-targets.spec.ts \
  e2e/deploy.spec.ts \
  e2e/agent-detail.spec.ts \
  e2e/dashboard-actions.spec.ts
```

Ergebnis:

- `8 passed`
- `2 skipped`

Die zwei Skips sind erwartbar:

- HAOS-Smoke in [`frontend/e2e/agent-detail.spec.ts`](/Users/jacques/Coding/patchpilot/frontend/e2e/agent-detail.spec.ts)
  - braucht `PP_E2E_HA_AGENT_ID`
- `Update Agents` in [`frontend/e2e/dashboard-actions.spec.ts`](/Users/jacques/Coding/patchpilot/frontend/e2e/dashboard-actions.spec.ts)
  - läuft nur, wenn auf der Testinstanz wirklich veraltete Agenten vorhanden sind

## Wichtige Env-Variablen

- `PP_E2E_BASE_URL`
- `PP_E2E_USERNAME`
- `PP_E2E_PASSWORD`
- `PP_E2E_LINUX_AGENT_ID`
- optional: `PP_E2E_HA_AGENT_ID`
- optional für frische HTTP->HTTPS-Regression:
  - `PP_E2E_RUN_SSL_ENABLE=1`
  - `PP_E2E_HTTP_BASE_URL`
  - `PP_E2E_HTTPS_BASE_URL`

## Hinweise

- Die Paket-Tests sind echte Integrations-Tests und erzeugen reale Jobs auf den Test-VMs.
- `Patch All` und Einzelpaket-Update wurden erfolgreich gegen die frische VM `Ubuntu` auf `.26` geprüft.
- Einzelpaket-Update, `Refresh Updates` und `Patch All` wurden erfolgreich gegen die frische VM `Test2` auf `.22` geprüft.
- `npm audit` im Frontend war nach Update auf `vite@6.4.2` und Override `picomatch@4.0.4` sauber:
  - `0 vulnerabilities`

## Standard-Workflow fuer kuenftige Integrations-Tests

Die sauberste Reihenfolge fuer Release- und Branch-Tests ist:

1. Frische Server-VM komplett leer starten
2. Aktuellen Stand lokal bauen
3. Echten Installationspfad wie ein Nutzer ausfuehren
   - nicht nur `deploy.sh`
   - sondern den normalen Installer / Build-Artefakt verwenden
4. Danach auf der frischen Instanz pruefen:
   - Login
   - Settings speichern
   - Zertifikat erzeugen / HTTPS aktivieren
   - Deploy / Register-Key
5. Erst danach frische Test-VMs mit dem echten Agent-Installer anbinden
6. Dann reale Flows pruefen:
   - Einzelpaket-Update
   - `Patch All`
   - `Refresh Updates`
   - optional `Update Agents`

Wichtig:

- Damit testen wir den echten Nutzerpfad inklusive `.env`, `PATCHPILOT_ADMIN_KEY`, Service-Datei, Rechte und Runtime.
- Reiner `deploy.sh`-Test reicht nicht fuer frische Instanzen, weil dadurch Setup-Luecken unentdeckt bleiben koennen.

## Letzter Fresh-Install-Lauf

Datum: `2026-04-13`

Server:

- `192.168.111.21` komplett geleert
- frischer Install aus dem aktuellen lokalen Branch ueber `install-server.sh`
- Admin-Login erfolgreich mit:
  - Benutzer: `admin`
  - Passwort: `duoTD0xNLpZIKvLd8DzyWA`

Agenten:

- `192.168.111.22` frisch angebunden als `Test2`
- `192.168.111.26` frisch angebunden als `Ubuntu`

Echte Checks:

- `admin`-Login auf frischer Instanz
- `GET /api/settings`
- `POST /api/register-key`
- `GET /api/deploy/bootstrap`
- frische Agent-Installation auf `.22` und `.26`
- Heartbeat / Paketinventar beider VMs
- Playwright gegen die frische Instanz:
  - `8 passed`
  - `2 skipped`
- Notification-Tests nach Uebernahme der `.20`-Konfiguration:
  - Email `sent`
  - Telegram `sent`
  - Push `sent`

Push-Regressionsfix nach dem Fresh-Install-Lauf:

- `POST /api/settings/push-mobile/activate` akzeptiert jetzt auch leere Requests robust
- wenn kein JSON-Body mitgegeben wird, faellt der Endpoint auf die bereits gespeicherte `webhook_url` zurueck
- auf `.21` danach live verifiziert:
  - `POST /api/settings/push-mobile/activate` -> `200`
  - `GET /api/push-config` -> `active=true`
  - `POST /api/settings/test/push` -> `sent`

Gefixte Installer-Funde aus diesem Lauf:

- `install-server.sh` darf keine lokale `server/patchpilot.db` mit uebernehmen
- Bootstrap-Cleanup darf die erste Passwort-Uebergabe nicht vorzeitig entfernen
- fuer frische Instanzen wird die DB-Datei vor dem ersten Start explizit mit Besitzer `patchpilot` angelegt
