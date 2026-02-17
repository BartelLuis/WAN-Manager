# WAN-Manager

Django-Anwendung zur Verwaltung von Standorten, WAN-Leitungen, Providern, Tarifen, Verträgen und WAN-Beauftragungen.

Diese Anleitung beschreibt die Installation auf **Windows** und **Linux**.  
Die Einrichtung des SQL-Servers ist **nicht** enthalten.

## Voraussetzungen

- Python `3.12+` (empfohlen: `3.13`)
- `pip`
- Ein bereits verfügbarer SQL-Server inkl. Datenbank/Benutzer
- Projektquellen (dieses Repository)

Hinweis: Das Projekt ist aktuell auf `django.db.backends.mysql` konfiguriert.

## 1. Projekt klonen

```bash
git clone <repo-url> WAN-Manager
cd WAN-Manager
```

## 2. Virtuelle Umgebung erstellen

### Windows (PowerShell)

```powershell
py -3.13 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### Linux (bash)

```bash
python3.13 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
```

## 3. Abhängigkeiten installieren

Da aktuell keine `requirements.txt` im Repository liegt:

```bash
pip install django mysqlclient
```

## 4. Datenbank-Konfiguration anpassen

Die DB-Verbindung steht in `config/settings.py` unter `DATABASES`.

Passe mindestens diese Werte an:

- `NAME`
- `USER`
- `PASSWORD`
- `HOST`
- `PORT`

## 5. Migrationen ausführen

```bash
python manage.py migrate
```

## 6. Admin-Benutzer anlegen (optional, empfohlen)

```bash
python manage.py createsuperuser
```

## 7. Entwicklungsserver starten

```bash
python manage.py runserver
```

Danach im Browser öffnen:

- `http://127.0.0.1:8000/`

## Nützliche Management-Commands

Standortkürzel nachträglich generieren (z. B. bei SQL-Importen):

```bash
python manage.py generate_standortkuerzel --dry-run
python manage.py generate_standortkuerzel
python manage.py generate_standortkuerzel --all
```

## Kurztest

```bash
python manage.py check
```

## Tests ohne MySQL-Rechte

Wenn der MySQL-User keine Berechtigung zum Erstellen der Testdatenbank hat, können Tests mit einer SQLite-Testkonfiguration laufen:

```bash
python manage.py test --settings=config.settings_test
```

## Hinweise für Produktion

- `DEBUG` in `config/settings.py` auf `False` setzen
- `SECRET_KEY` nicht im Code hinterlegen
- `ALLOWED_HOSTS` korrekt setzen
- Statische Dateien sammeln:

```bash
python manage.py collectstatic
```

## Produktiver Betrieb (WSGI) je OS

### Windows: Waitress (WSGI) als Dienst

1. Abhängigkeit installieren:

```powershell
pip install waitress
```

2. Testlauf (ohne Dienst):

```powershell
.\venv\Scripts\waitress-serve.exe --listen=0.0.0.0:8000 config.wsgi:application
```

3. Als Windows-Dienst betreiben (NSSM):

NSSM Download: `https://nssm.cc/download`  
Danach z. B. nach `C:\tools\nssm\` entpacken.

4. Dienst anlegen (PowerShell als Administrator):

```powershell
C:\tools\nssm\win64\nssm.exe install WAN-Manager
```

Im NSSM-Dialog setzen:
- `Application Path`: `C:\...\WAN-Manager\venv\Scripts\waitress-serve.exe`
- `Startup directory`: `C:\...\WAN-Manager`
- `Arguments`: `--listen=127.0.0.1:8000 config.wsgi:application`

Optional im Tab `I/O`:
- `Output (stdout)`: `C:\...\WAN-Manager\logs\wan-manager-out.log`
- `Error (stderr)`: `C:\...\WAN-Manager\logs\wan-manager-err.log`

5. Dienst starten und prüfen:

```powershell
sc start WAN-Manager
sc query WAN-Manager
```

6. Autostart konfigurieren:

```powershell
sc config WAN-Manager start= auto
```

7. Wartung:

```powershell
sc stop WAN-Manager
sc start WAN-Manager
sc delete WAN-Manager
```

Optional: Vor Waitress einen Reverse Proxy (IIS/Nginx) für TLS (HTTPS) setzen.

### Linux: Gunicorn (WSGI) + systemd

1. Abhängigkeit installieren:

```bash
pip install gunicorn
```

2. Testlauf:

```bash
./venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 config.wsgi:application
```

3. systemd Service anlegen, z. B. `/etc/systemd/system/wan-manager.service`:

```ini
[Unit]
Description=WAN-Manager (Gunicorn)
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/WAN-Manager
Environment="PATH=/opt/WAN-Manager/venv/bin"
ExecStart=/opt/WAN-Manager/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 config.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

4. Aktivieren und starten:

```bash
sudo systemctl daemon-reload
sudo systemctl enable wan-manager
sudo systemctl start wan-manager
sudo systemctl status wan-manager
```

Optional: Nginx als Reverse Proxy vor Gunicorn (HTTPS, Header, Caching statischer Inhalte).

## Minimaler Produktions-Check

```bash
python manage.py check --deploy
```
