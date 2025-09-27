#!/usr/bin/env python3
"""
Simple sign‑in application for ABA providers.

This script implements a small web server using Python's built‑in
`http.server` module. It serves HTML pages that allow administrators
to load staff, client, and schedule data from CSV files and provides
interfaces for staff and clients to sign in/out. It also produces
reports to help administrators quickly identify which individuals are
on‑site or missing relative to their schedules. The goal of this
script is to demonstrate a minimal, self‑contained visitor management
tool that can run without any third‑party dependencies.

Key features:

* Upload CSV files containing staff, clients, and schedules. The
  expected formats are described in the `data` directory. Each row
  should have a unique identifier and contact details.
* Sign in/out pages for staff and clients. Individuals can select
  their name from a dropdown and record their arrival or departure.
* Admin dashboard that shows the current sign‑in status, compares
  attendance against the day's schedule, and highlights absences.
* Emergency roll‑call page that lists everyone scheduled to be on
  site and indicates who is accounted for. Contact details for
  missing individuals are provided so administrators can quickly
  reach designated contacts.

This server is designed for demonstration purposes. It keeps all
information in memory and writes simple JSON snapshots to the
``runtime`` directory so that the state survives a server restart.
For a production system you would likely replace these structures
with a proper database and authentication system.
"""

import csv
import datetime
import json
import os
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
from io import BytesIO
from urllib.parse import parse_qs
import cgi

# Base directory of this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Directory where runtime files (snapshots) are stored
RUNTIME_DIR = os.path.join(BASE_DIR, 'runtime')
os.makedirs(RUNTIME_DIR, exist_ok=True)

# Global in‑memory storage
DATA = {
    'staff': {},    # id -> {id, name, email, phone, site, contact_name, contact_phone}
    'clients': {},  # id -> {id, name, contact_name, contact_phone, site}
    'schedule': [], # list of {person_type, id, date, start_time, end_time, site}
    'signins': []   # list of {person_type, id, name, site, timestamp, action}
}


def load_csv(file_path: str, category: str) -> None:
    """Load staff or client data from a CSV file.

    Parameters
    ----------
    file_path : str
        Path to the CSV file.
    category : str
        Either 'staff' or 'clients'. Determines how the records are stored.

    The CSV for staff should have columns:
        id,name,email,phone,site,contact_name,contact_phone

    The CSV for clients should have columns:
        id,name,contact_name,contact_phone,site

    This function clears any existing records in the selected category.
    """
    DATA[category] = {}
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            key = row.get('id') or row.get('ID')
            if not key:
                continue
            # Normalize keys to lower case for uniform access
            record = {k.lower(): v.strip() for k, v in row.items()}
            DATA[category][key] = record


def load_schedule_csv(file_path: str) -> None:
    """Load schedule data from a CSV file.

    The schedule CSV should have columns:
        person_type,id,date,start_time,end_time,site

    where
        * person_type is 'staff' or 'client'
        * id references the ID of the staff or client
        * date is in YYYY-MM-DD format
        * start_time and end_time are in HH:MM (24h) format
        * site corresponds to a location name

    Existing schedule entries are cleared when this function runs.
    """
    DATA['schedule'] = []
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            person_type = row.get('person_type', '').strip().lower()
            pid = row.get('id', '').strip()
            date_str = row.get('date', '').strip()
            start_time = row.get('start_time', '').strip()
            end_time = row.get('end_time', '').strip()
            site = row.get('site', '').strip()
            if not (person_type and pid and date_str and start_time and end_time and site):
                continue
            # Validate person type
            if person_type not in ('staff', 'client'):
                continue
            # Validate date
            try:
                datetime.datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                continue
            # Basic time validation
            if len(start_time) < 4 or len(end_time) < 4:
                continue
            DATA['schedule'].append({
                'person_type': person_type,
                'id': pid,
                'date': date_str,
                'start_time': start_time,
                'end_time': end_time,
                'site': site
            })


def save_runtime_state() -> None:
    """Save the current sign‑in records to disk as JSON.

    This allows the state to be preserved across server restarts. Only
    sign‑in records are stored in the runtime snapshot because staff,
    client, and schedule data are typically loaded from CSV files.
    """
    snapshot_path = os.path.join(RUNTIME_DIR, 'signins.json')
    with open(snapshot_path, 'w', encoding='utf-8') as f:
        json.dump(DATA['signins'], f, indent=2)


def load_runtime_state() -> None:
    """Load sign‑in records from disk if they exist."""
    snapshot_path = os.path.join(RUNTIME_DIR, 'signins.json')
    if os.path.isfile(snapshot_path):
        try:
            with open(snapshot_path, 'r', encoding='utf-8') as f:
                DATA['signins'] = json.load(f)
        except Exception:
            DATA['signins'] = []
    else:
        DATA['signins'] = []


class SignInHTTPRequestHandler(BaseHTTPRequestHandler):
    """Request handler for the sign‑in application.

    This handler serves HTML pages for signing in/out, uploading CSV files,
    and viewing the admin dashboard. It uses simple string templates
    constructed in Python without any templating library. All pages
    reference bootstrap CSS via CDN for basic styling.
    """

    def _send_response(self, content: bytes, content_type: str = 'text/html', status: HTTPStatus = HTTPStatus.OK):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/':
            self._serve_home()
        elif path == '/admin':
            self._serve_admin()
        elif path == '/emergency':
            self._serve_emergency()
        elif path == '/load_data':
            self._serve_load_data_page()
        elif path.startswith('/static/'):
            self._serve_static(path)
        else:
            self._send_response(b'Not found', 'text/plain', HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = self.path.split('?')[0]
        if path == '/sign_action':
            self._handle_sign_action()
        elif path == '/upload_csv':
            self._handle_upload_csv()
        else:
            self._send_response(b'Not found', 'text/plain', HTTPStatus.NOT_FOUND)

    # Static file serving (limited to CSS)
    def _serve_static(self, path: str):
        file_path = os.path.join(BASE_DIR, path.lstrip('/'))
        if not os.path.isfile(file_path):
            self._send_response(b'File not found', 'text/plain', HTTPStatus.NOT_FOUND)
            return
        with open(file_path, 'rb') as f:
            content = f.read()
        content_type = 'text/css' if file_path.endswith('.css') else 'application/octet-stream'
        self._send_response(content, content_type)

    # Page templates
    def _html_template(self, title: str, body: str) -> bytes:
        """Wrap the provided body in a simple HTML document."""
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css">
</head>
<body class="bg-light">
<nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
  <div class="container-fluid">
    <a class="navbar-brand" href="/">ABA Sign In</a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="navbarNav">
      <ul class="navbar-nav">
        <li class="nav-item"><a class="nav-link" href="/">Home</a></li>
        <li class="nav-item"><a class="nav-link" href="/admin">Admin</a></li>
        <li class="nav-item"><a class="nav-link" href="/emergency">Emergency</a></li>
        <li class="nav-item"><a class="nav-link" href="/load_data">Load Data</a></li>
      </ul>
    </div>
  </div>
</nav>
<div class="container">
  {body}
</div>
</body>
</html>
"""
        return html.encode('utf-8')

    def _serve_home(self):
        """Serve the home page with sign‑in/out forms."""
        # Build options for staff and clients
        staff_options = ''.join([f'<option value="staff|{sid}">{rec.get("name", "")}</option>' for sid, rec in DATA['staff'].items()])
        client_options = ''.join([f'<option value="client|{cid}">{rec.get("name", "")}</option>' for cid, rec in DATA['clients'].items()])
        body = f"""
<div class="row">
  <div class="col-md-6">
    <h2>Staff Sign In/Out</h2>
    <form method="post" action="/sign_action">
      <div class="mb-3">
        <label for="staff_select" class="form-label">Select staff member</label>
        <select class="form-select" id="staff_select" name="person" required>
          <option value="">-- Choose staff --</option>
          {staff_options}
        </select>
      </div>
      <div class="mb-3">
        <label class="form-label">Action</label><br>
        <div class="form-check form-check-inline">
          <input class="form-check-input" type="radio" name="action" id="staff_in" value="sign_in" checked>
          <label class="form-check-label" for="staff_in">Sign In</label>
        </div>
        <div class="form-check form-check-inline">
          <input class="form-check-input" type="radio" name="action" id="staff_out" value="sign_out">
          <label class="form-check-label" for="staff_out">Sign Out</label>
        </div>
      </div>
      <div class="mb-3">
        <label for="staff_site" class="form-label">Site</label>
        <input type="text" class="form-control" id="staff_site" name="site" placeholder="e.g. Fort Wayne" required>
      </div>
      <button type="submit" class="btn btn-primary">Submit</button>
    </form>
  </div>
  <div class="col-md-6">
    <h2>Client Sign In/Out</h2>
    <form method="post" action="/sign_action">
      <div class="mb-3">
        <label for="client_select" class="form-label">Select client</label>
        <select class="form-select" id="client_select" name="person" required>
          <option value="">-- Choose client --</option>
          {client_options}
        </select>
      </div>
      <div class="mb-3">
        <label class="form-label">Action</label><br>
        <div class="form-check form-check-inline">
          <input class="form-check-input" type="radio" name="action" id="client_in" value="sign_in" checked>
          <label class="form-check-label" for="client_in">Sign In</label>
        </div>
        <div class="form-check form-check-inline">
          <input class="form-check-input" type="radio" name="action" id="client_out" value="sign_out">
          <label class="form-check-label" for="client_out">Sign Out</label>
        </div>
      </div>
      <div class="mb-3">
        <label for="client_site" class="form-label">Site</label>
        <input type="text" class="form-control" id="client_site" name="site" placeholder="e.g. Fort Wayne" required>
      </div>
      <button type="submit" class="btn btn-primary">Submit</button>
    </form>
  </div>
</div>
"""
        self._send_response(self._html_template('Home - ABA Sign In', body))

    def _handle_sign_action(self):
        """Process a sign‑in or sign‑out form submission."""
        ctype, pdict = cgi.parse_header(self.headers.get('Content-Type'))
        if ctype == 'multipart/form-data':
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD': 'POST'})
        else:
            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length).decode('utf-8')
            form = parse_qs(data)
        # Extract fields
        person_field = form.get('person')
        action_field = form.get('action')
        site_field = form.get('site')
        if isinstance(person_field, list):
            person_field = person_field[0]
        if isinstance(action_field, list):
            action_field = action_field[0]
        if isinstance(site_field, list):
            site_field = site_field[0]
        if not (person_field and action_field and site_field):
            self._send_response(self._html_template('Error', '<p class="text-danger">Invalid form submission.</p>'))
            return
        # person_field is of the form "type|id"
        try:
            ptype, pid = person_field.split('|')
        except ValueError:
            self._send_response(self._html_template('Error', '<p class="text-danger">Invalid person selected.</p>'))
            return
        # Get name
        record = DATA['staff'].get(pid) if ptype == 'staff' else DATA['clients'].get(pid)
        name = record.get('name') if record else pid
        timestamp = datetime.datetime.now().isoformat(timespec='seconds')
        # Record the sign action
        DATA['signins'].append({
            'person_type': ptype,
            'id': pid,
            'name': name,
            'site': site_field,
            'timestamp': timestamp,
            'action': action_field
        })
        save_runtime_state()
        # Response
        message = f"Successfully recorded {action_field.replace('_', ' ').title()} for {name} at {timestamp}".replace('_', ' ')
        body = f'<div class="alert alert-success" role="alert">{message}</div><a href="/" class="btn btn-primary">Return to Home</a>'
        self._send_response(self._html_template('Submission Received', body))

    def _serve_admin(self):
        """Serve the admin dashboard with sign‑in history and schedule comparison."""
        today = datetime.date.today().isoformat()
        # Determine current sign‑ins (last action per person)
        last_actions = {}
        for record in DATA['signins']:
            last_actions[(record['person_type'], record['id'])] = record
        current_on_site = [rec for rec in last_actions.values() if rec['action'] == 'sign_in']
        # Determine scheduled persons for today
        scheduled_today = [s for s in DATA['schedule'] if s['date'] == today]
        # Build table of schedule vs sign‑in
        rows = []
        for s in scheduled_today:
            key = (s['person_type'], s['id'])
            status = 'Absent'
            sign_time = ''
            site = s['site']
            name = ''
            # Find person record
            if s['person_type'] == 'staff':
                rec = DATA['staff'].get(s['id'])
                name = rec.get('name', s['id']) if rec else s['id']
            else:
                rec = DATA['clients'].get(s['id'])
                name = rec.get('name', s['id']) if rec else s['id']
            if key in last_actions and last_actions[key]['action'] == 'sign_in':
                status = 'Present'
                sign_time = last_actions[key]['timestamp']
            rows.append((s['person_type'].title(), name, s['start_time'], s['end_time'], site, status, sign_time))
        # HTML table rows
        table_rows = ''.join([f'<tr><td>{ptype}</td><td>{name}</td><td>{start}</td><td>{end}</td><td>{site}</td><td>{status}</td><td>{stime}</td></tr>' for (ptype, name, start, end, site, status, stime) in rows])
        # Build sign-in history table rows separately to avoid quoting issues in f-string
        history_entries = []
        for rec in DATA['signins'][-20:][::-1]:
            # Format action string by replacing underscores
            action_str = rec['action'].replace('_', ' ').title()
            history_entries.append(
                f"<tr><td>{rec['timestamp']}</td><td>{rec['person_type'].title()}</td><td>{rec['name']}</td><td>{rec['site']}</td><td>{action_str}</td></tr>"
            )
        history_rows = ''.join(history_entries)
        body = f"""
<h2>Admin Dashboard</h2>
<p>Today is {today}</p>
<h3>Schedule vs Attendance</h3>
<table class="table table-striped">
  <thead>
    <tr><th>Type</th><th>Name</th><th>Start</th><th>End</th><th>Site</th><th>Status</th><th>Sign Time</th></tr>
  </thead>
  <tbody>
    {table_rows}
  </tbody>
</table>
<h3>Sign‑In History (latest 20 entries)</h3>
<table class="table table-bordered">
  <thead>
    <tr><th>Timestamp</th><th>Type</th><th>Name</th><th>Site</th><th>Action</th></tr>
  </thead>
  <tbody>
            {history_rows}
  </tbody>
</table>
"""
        self._send_response(self._html_template('Admin Dashboard', body))

    def _serve_emergency(self):
        """Serve the emergency page showing who's on site and who is missing."""
        today = datetime.date.today().isoformat()
        # Last action for each person
        last_actions = {}
        for record in DATA['signins']:
            last_actions[(record['person_type'], record['id'])] = record
        scheduled_today = [s for s in DATA['schedule'] if s['date'] == today]
        present = []
        missing = []
        for s in scheduled_today:
            key = (s['person_type'], s['id'])
            record = None
            name = ''
            contact_name = ''
            contact_phone = ''
            if s['person_type'] == 'staff':
                person = DATA['staff'].get(s['id'])
                name = person.get('name', s['id']) if person else s['id']
                contact_name = person.get('contact_name', '') if person else ''
                contact_phone = person.get('contact_phone', '') if person else ''
            else:
                person = DATA['clients'].get(s['id'])
                name = person.get('name', s['id']) if person else s['id']
                contact_name = person.get('contact_name', '') if person else ''
                contact_phone = person.get('contact_phone', '') if person else ''
            if key in last_actions and last_actions[key]['action'] == 'sign_in':
                record = last_actions[key]
                present.append((s['person_type'].title(), name, record['site'], record['timestamp']))
            else:
                missing.append((s['person_type'].title(), name, s['site'], contact_name, contact_phone))
        # Build tables
        present_rows = ''.join([f'<tr><td>{ptype}</td><td>{name}</td><td>{site}</td><td>{time}</td></tr>' for (ptype, name, site, time) in present])
        missing_rows = ''.join([f'<tr><td>{ptype}</td><td>{name}</td><td>{site}</td><td>{cname}</td><td>{cphone}</td></tr>' for (ptype, name, site, cname, cphone) in missing])
        body = f"""
<h2>Emergency Roll Call</h2>
<p>Date: {today}</p>
<h3>Present on Site</h3>
<table class="table table-success table-bordered">
  <thead><tr><th>Type</th><th>Name</th><th>Site</th><th>Signed In At</th></tr></thead>
  <tbody>
    {present_rows or '<tr><td colspan="4">No one is currently signed in according to records.</td></tr>'}
  </tbody>
</table>
<h3>Scheduled but Missing</h3>
<table class="table table-danger table-bordered">
  <thead><tr><th>Type</th><th>Name</th><th>Expected Site</th><th>Contact Name</th><th>Contact Phone</th></tr></thead>
  <tbody>
    {missing_rows or '<tr><td colspan="5">No one is missing according to schedule.</td></tr>'}
  </tbody>
</table>
"""
        self._send_response(self._html_template('Emergency Roll Call', body))

    def _serve_load_data_page(self):
        """Serve the page for uploading CSV files."""
        body = """
<h2>Load Data</h2>
<p>Use this page to upload CSV files for staff, clients, and schedules. The server will overwrite existing data in memory.</p>
<div class="row">
  <div class="col-md-4">
    <h4>Upload Staff CSV</h4>
    <form method="post" action="/upload_csv" enctype="multipart/form-data">
      <input type="hidden" name="category" value="staff">
      <div class="mb-3">
        <input class="form-control" type="file" name="file" accept=".csv" required>
      </div>
      <button type="submit" class="btn btn-primary">Upload Staff</button>
    </form>
  </div>
  <div class="col-md-4">
    <h4>Upload Clients CSV</h4>
    <form method="post" action="/upload_csv" enctype="multipart/form-data">
      <input type="hidden" name="category" value="clients">
      <div class="mb-3">
        <input class="form-control" type="file" name="file" accept=".csv" required>
      </div>
      <button type="submit" class="btn btn-primary">Upload Clients</button>
    </form>
  </div>
  <div class="col-md-4">
    <h4>Upload Schedule CSV</h4>
    <form method="post" action="/upload_csv" enctype="multipart/form-data">
      <input type="hidden" name="category" value="schedule">
      <div class="mb-3">
        <input class="form-control" type="file" name="file" accept=".csv" required>
      </div>
      <button type="submit" class="btn btn-primary">Upload Schedule</button>
    </form>
  </div>
</div>
"""
        self._send_response(self._html_template('Load Data', body))

    def _handle_upload_csv(self):
        """Handle CSV uploads for staff, clients, and schedule."""
        # Parse the incoming form data. Use cgi.FieldStorage to support file upload.
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD': 'POST'})
        category = form.getvalue('category')
        fileitem = form['file'] if 'file' in form else None
        if (
            category not in ('staff', 'clients', 'schedule')
            or fileitem is None
            or getattr(fileitem, 'file', None) is None
        ):
            self._send_response(self._html_template('Error', '<p class="text-danger">Invalid upload request.</p>'))
            return
        # Save the uploaded file to a temporary location
        upload_path = os.path.join(RUNTIME_DIR, f'tmp_upload_{category}.csv')
        with open(upload_path, 'wb') as fout:
            while True:
                chunk = fileitem.file.read(8192)
                if not chunk:
                    break
                fout.write(chunk)
        # Load into memory
        try:
            if category in ('staff', 'clients'):
                load_csv(upload_path, category)
            else:
                load_schedule_csv(upload_path)
        except Exception as e:
            body = f'<p class="text-danger">Error processing CSV: {e}</p>'
            self._send_response(self._html_template('Upload Error', body))
            return
        body = f'<div class="alert alert-success" role="alert">Successfully loaded {category} data.</div><a href="/load_data" class="btn btn-primary">Back to Load Data</a>'
        self._send_response(self._html_template('Upload Successful', body))


def _initial_data_paths(filename: str):
    """Yield potential CSV locations for bundled starter data."""
    # Prefer files stored in the optional ``data`` subdirectory but fall back to
    # CSVs located next to ``app.py``. The repository already ships sample
    # ``staff.csv``, ``clients.csv`` and ``schedule.csv`` files in the project
    # root, so checking both locations lets the application work out-of-the-box
    # without any manual uploads.
    yield os.path.join(BASE_DIR, 'data', filename)
    yield os.path.join(BASE_DIR, filename)


def run_server(port: int = 8000):
    """Initialize data from runtime snapshot and start the HTTP server."""
    load_runtime_state()
    # Optionally pre-load CSVs if present in either the ``data`` directory or
    # alongside this script. The first matching path wins so users can override
    # the bundled examples by dropping replacement files into ``data/``.
    for category in ('staff', 'clients'):
        for csv_path in _initial_data_paths(f'{category}.csv'):
            if not os.path.isfile(csv_path):
                continue
            try:
                load_csv(csv_path, category)
                break
            except Exception:
                # Try the next candidate file if parsing fails.
                continue
    for csv_path in _initial_data_paths('schedule.csv'):
        if not os.path.isfile(csv_path):
            continue
        try:
            load_schedule_csv(csv_path)
            break
        except Exception:
            continue
    server = HTTPServer(('0.0.0.0', port), SignInHTTPRequestHandler)
    print(f"Server starting on http://localhost:{port} ...")
    server.serve_forever()


if __name__ == '__main__':
    run_server()
