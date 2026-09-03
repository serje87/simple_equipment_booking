# Equipment Booking — local deployment

The service uses only the Python standard library and SQLite. It does not need
internet access while running.

## Requirements

- Python 3.11 or newer

## Start

```bash
python3 app.py
```

Open `http://SERVER_IP:8080` in a browser. Stop the application with `Ctrl+C`.

The database is created automatically in `data/equipment.db`. If no `ADMIN_CODE`
environment variable is set, the generated administrator code is printed at
startup and stored in `data/admin_code.txt`.

## Page title

Change this setting near the top of `app.py`:

```python
PAGE_TITLE = "Lab Equipment"
```

The value is used both in the page header and in the browser tab. Restart the
application after changing it.

## Equipment management

Stop the service before manually editing the SQLite file, or use the included
utility:

```bash
python3 manage.py list
python3 manage.py add "Device name" "Description" --address "lab-pc-01" --rdp
python3 manage.py update 1 --address "192.168.1.25" --rdp on --ssh on
python3 manage.py update 1 --clear-address --rdp off --ssh off
python3 manage.py delete 1
```

## RDP button mode

By default, the RDP button downloads a standard `.rdp` file. To open an
installed `rdp://` protocol handler instead, change this setting in `app.py`:

```python
RDP_LINK_MODE = "protocol"
```

Set it back to `"download"` to restore `.rdp` downloads, then restart the
application.

## Offline deployment

Copy this entire folder to the target machine and run `python3 app.py`. No
package installation or internet connection is required.

The application listens on port `8080`, so a reverse proxy can forward HTTP
traffic to `127.0.0.1:8080`.

## Ownership model

Ownership is matched by the exact user-name string. Entering the same name again
allows the user to release bookings made under that name. A different name
cannot release them unless the administrator code is supplied.
