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
import html
import io
import os
from dataclasses import dataclass
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Iterable, Mapping, Optional
from urllib.parse import parse_qs, urlparse
import cgi
import email.message

from aba_enterprise import (
    AppConfig,
    AuditLogger,
    CSVDataLoader,
    EmergencyNotificationService,
    ReportingService,
    RuntimeSnapshotStore,
    SettingsStore,
    SignInService,
    configure_logging,
    load_app_config,
)

# Base directory of this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Directory where runtime files (snapshots) are stored
APP_CONFIG: AppConfig = load_app_config(BASE_DIR)
configure_logging(APP_CONFIG)
RUNTIME_DIR = str(APP_CONFIG.runtime_dir)
os.makedirs(RUNTIME_DIR, exist_ok=True)

# Global in‑memory storage
DATA = {
    'staff': {},    # id -> {id, name, email, phone, site, contact_name, contact_phone}
    'clients': {},  # id -> {id, name, contact_name, contact_phone, site}
    'schedule': [], # list of {person_type, id, date, start_time, end_time, site}
    'signins': []   # list of {person_type, id, name, site, timestamp, action}
}

# Runtime settings such as configured webhooks
SETTINGS = {
    'teams_webhook_url': ''
}

DATA_LOADER = CSVDataLoader(DATA)
REPORTING_SERVICE = ReportingService(DATA)


FIRE_DRILL_REASON_OPTIONS = [
    "On community outing",
    "Offsite appointment",
    "Sick/Called off",
    "Staffed remotely",
    "Transport delay",
    "Other",
]


def _reason_field_name(person: Mapping[str, str]) -> str:
    person_type = person.get('person_type', '').lower().replace(' ', '_')
    identifier = person.get('person_id', '')
    return f"reason_{person_type}_{identifier}"


@dataclass
class AppResponse:
    """Simple representation of an HTTP response produced by the app router."""

    status: HTTPStatus
    headers: Dict[str, str]
    body: bytes


def _html_template(title: str, body: str) -> bytes:
    """Wrap the provided body in a standard HTML template."""

    html_doc = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>{title}</title>
  <link rel=\"stylesheet\" href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css\">
</head>
<body class=\"bg-light\">
<nav class=\"navbar navbar-expand-lg navbar-dark bg-primary mb-4\">
  <div class=\"container-fluid\">
    <a class=\"navbar-brand\" href=\"/\">ABA Sign In</a>
    <button class=\"navbar-toggler\" type=\"button\" data-bs-toggle=\"collapse\" data-bs-target=\"#navbarNav\" aria-controls=\"navbarNav\" aria-expanded=\"false\" aria-label=\"Toggle navigation\">
      <span class=\"navbar-toggler-icon\"></span>
    </button>
    <div class=\"collapse navbar-collapse\" id=\"navbarNav\">
      <ul class=\"navbar-nav\">
        <li class=\"nav-item\"><a class=\"nav-link\" href=\"/\">Home</a></li>
        <li class=\"nav-item\"><a class=\"nav-link\" href=\"/admin\">Admin</a></li>
        <li class=\"nav-item\"><a class=\"nav-link\" href=\"/emergency\">Emergency</a></li>
        <li class=\"nav-item\"><a class=\"nav-link\" href=\"/load_data\">Load Data</a></li>
      </ul>
    </div>
  </div>
</nav>
<div class=\"container\">
  {body}
</div>
</body>
</html>"""
    return html_doc.encode("utf-8")


def _html_response(title: str, body: str, status: HTTPStatus = HTTPStatus.OK,
                   extra_headers: Optional[Mapping[str, str]] = None) -> AppResponse:
    content = _html_template(title, body)
    headers = {"Content-Type": "text/html; charset=utf-8", "Content-Length": str(len(content))}
    if extra_headers:
        headers.update(extra_headers)
    return AppResponse(status=status, headers=headers, body=content)


def _text_response(body: str, status: HTTPStatus = HTTPStatus.OK,
                   content_type: str = "text/plain") -> AppResponse:
    headers = {"Content-Type": content_type, "Content-Length": str(len(body.encode("utf-8")))}
    return AppResponse(status=status, headers=headers, body=body.encode("utf-8"))


def _parse_urlencoded(body: bytes) -> Dict[str, str]:
    if not body:
        return {}
    data = parse_qs(body.decode('utf-8'), keep_blank_values=True)
    result: Dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, list):
            result[key] = value[0]
        else:
            result[key] = value
    return result


def _build_message_from_headers(headers: Mapping[str, str]) -> email.message.Message:
    msg = email.message.Message()
    for key, value in headers.items():
        msg[key] = value
    return msg


def _parse_multipart_form(headers: Mapping[str, str], body: bytes) -> cgi.FieldStorage:
    environ = {
        'REQUEST_METHOD': 'POST',
        'CONTENT_TYPE': headers.get('Content-Type', ''),
    }
    content_length = headers.get('Content-Length') or str(len(body))
    environ['CONTENT_LENGTH'] = content_length
    message = headers if isinstance(headers, email.message.Message) else _build_message_from_headers(headers)
    return cgi.FieldStorage(fp=io.BytesIO(body), headers=message, environ=environ)


def _home_body() -> str:
    staff_options = ''.join(
        [f'<option value="staff|{sid}">{html.escape(rec.get("name", ""))}</option>' for sid, rec in DATA['staff'].items()]
    )
    client_options = ''.join(
        [f'<option value="client|{cid}">{html.escape(rec.get("name", ""))}</option>' for cid, rec in DATA['clients'].items()]
    )
    return f"""
<div class=\"row\">
  <div class=\"col-md-6\">
    <h2>Staff Sign In/Out</h2>
    <form method=\"post\" action=\"/sign_action\">
      <div class=\"mb-3\">
        <label for=\"staff_select\" class=\"form-label\">Select staff member</label>
        <select class=\"form-select\" id=\"staff_select\" name=\"person\" required>
          <option value=\"\">-- Choose staff --</option>
          {staff_options}
        </select>
      </div>
      <div class=\"mb-3\">
        <label class=\"form-label\">Action</label><br>
        <div class=\"form-check form-check-inline\">
          <input class=\"form-check-input\" type=\"radio\" name=\"action\" id=\"staff_in\" value=\"sign_in\" checked>
          <label class=\"form-check-label\" for=\"staff_in\">Sign In</label>
        </div>
        <div class=\"form-check form-check-inline\">
          <input class=\"form-check-input\" type=\"radio\" name=\"action\" id=\"staff_out\" value=\"sign_out\">
          <label class=\"form-check-label\" for=\"staff_out\">Sign Out</label>
        </div>
      </div>
      <div class=\"mb-3\">
        <label for=\"staff_site\" class=\"form-label\">Site</label>
        <input type=\"text\" class=\"form-control\" id=\"staff_site\" name=\"site\" placeholder=\"e.g. Fort Wayne\" required>
      </div>
      <button type=\"submit\" class=\"btn btn-primary\">Submit</button>
    </form>
  </div>
  <div class=\"col-md-6\">
    <h2>Client Sign In/Out</h2>
    <form method=\"post\" action=\"/sign_action\">
      <div class=\"mb-3\">
        <label for=\"client_select\" class=\"form-label\">Select client</label>
        <select class=\"form-select\" id=\"client_select\" name=\"person\" required>
          <option value=\"\">-- Choose client --</option>
          {client_options}
        </select>
      </div>
      <div class=\"mb-3\">
        <label class=\"form-label\">Action</label><br>
        <div class=\"form-check form-check-inline\">
          <input class=\"form-check-input\" type=\"radio\" name=\"action\" id=\"client_in\" value=\"sign_in\" checked>
          <label class=\"form-check-label\" for=\"client_in\">Sign In</label>
        </div>
        <div class=\"form-check form-check-inline\">
          <input class=\"form-check-input\" type=\"radio\" name=\"action\" id=\"client_out\" value=\"sign_out\">
          <label class=\"form-check-label\" for=\"client_out\">Sign Out</label>
        </div>
      </div>
      <div class=\"mb-3\">
        <label for=\"client_site\" class=\"form-label\">Site</label>
        <input type=\"text\" class=\"form-control\" id=\"client_site\" name=\"site\" placeholder=\"e.g. Fort Wayne\" required>
      </div>
      <button type=\"submit\" class=\"btn btn-primary\">Submit</button>
    </form>
  </div>
</div>
"""


def home_response() -> AppResponse:
    return _html_response("Home - ABA Sign In", _home_body())


def _admin_body() -> str:
    today = datetime.date.today().isoformat()
    rows = REPORTING_SERVICE.build_schedule_matrix(today)
    table_rows = ''.join(
        [
            f"<tr><td>{row['person_type']}</td><td>{row['name']}</td><td>{row['start_time']}</td>"
            f"<td>{row['end_time']}</td><td>{row['site']}</td><td>{row['status']}</td><td>{row['sign_time']}</td></tr>"
            for row in rows
        ]
    )
    history_entries = []
    for rec in DATA['signins'][-20:][::-1]:
        action_str = rec['action'].replace('_', ' ').title()
        history_entries.append(
            f"<tr><td>{rec['timestamp']}</td><td>{rec['person_type'].title()}</td><td>{rec['name']}</td>"
            f"<td>{rec['site']}</td><td>{action_str}</td></tr>"
        )
    history_rows = ''.join(history_entries)
    return f"""
<h2>Admin Dashboard</h2>
<p>Today is {today}</p>
<h3>Schedule vs Attendance</h3>
<table class=\"table table-striped\">
  <thead>
    <tr><th>Type</th><th>Name</th><th>Start</th><th>End</th><th>Site</th><th>Status</th><th>Sign Time</th></tr>
  </thead>
  <tbody>
    {table_rows}
  </tbody>
</table>
<h3>Sign‑In History (latest 20 entries)</h3>
<table class=\"table table-bordered\">
  <thead>
    <tr><th>Timestamp</th><th>Type</th><th>Name</th><th>Site</th><th>Action</th></tr>
  </thead>
  <tbody>
            {history_rows}
  </tbody>
</table>
"""


def admin_response() -> AppResponse:
    return _html_response("Admin Dashboard", _admin_body())


def _emergency_body() -> str:
    status = build_emergency_status()
    present_rows = ''.join(
        [
            '<tr>'
            f"<td>{html.escape(person.get('person_type', ''))}</td>"
            f"<td>{html.escape(person.get('name', ''))}</td>"
            f"<td>{html.escape(person.get('site', ''))}</td>"
            f"<td>{html.escape(person.get('timestamp', ''))}</td>"
            '</tr>'
            for person in status['present']
        ]
    )
    missing_rows = ''.join(
        [
            '<tr>'
            f"<td>{html.escape(person.get('person_type', ''))}</td>"
            f"<td>{html.escape(person.get('name', ''))}</td>"
            f"<td>{html.escape(person.get('site', ''))}</td>"
            f"<td>{html.escape(person.get('contact_name', ''))}</td>"
            f"<td>{html.escape(person.get('contact_phone', ''))}</td>"
            '</tr>'
            for person in status['missing']
        ]
    )
    if SETTINGS.get('teams_webhook_url'):
        preview_markdown = format_emergency_markdown(status)
        preview_html = html.escape(preview_markdown).replace('\n', '<br>')
        teams_notice = (
            "<form method=\"post\" action=\"/notify_teams\">"
            "  <button type=\"submit\" class=\"btn btn-warning mb-3\">Send Teams Emergency Notification</button>"
            "</form>"
            "<p class=\"text-muted\">A notification will be posted to the configured Microsoft Teams channel.</p>"
            "<details class=\"mb-3\">"
            "  <summary>Preview Teams message</summary>"
            f"  <div class=\"mt-2 p-3 bg-white border rounded\">{preview_html}</div>"
            "</details>"
        )
    else:
        teams_notice = (
            "<div class=\"alert alert-info\" role=\"alert\">"
            "Configure a Microsoft Teams webhook on the Load Data page to enable emergency notifications."
            "</div>"
        )
    button = (
        '<a class="btn btn-success mb-3" href="/firedrill_report">Complete Fire Drill Report</a>'
        if status['present'] or status['missing']
        else ''
    )
    return f"""
<h2>Emergency Roll Call</h2>
<p>Report for {status['date']}</p>
{teams_notice}
{button}
<h3>Present on Site</h3>
<table class=\"table table-success table-bordered\">
  <thead><tr><th>Type</th><th>Name</th><th>Site</th><th>Signed In At</th></tr></thead>
  <tbody>
    {present_rows or '<tr><td colspan=\"4\">No one is currently signed in according to records.</td></tr>'}
  </tbody>
</table>
<h3>Scheduled but Missing</h3>
<table class=\"table table-danger table-bordered\">
  <thead><tr><th>Type</th><th>Name</th><th>Expected Site</th><th>Contact Name</th><th>Contact Phone</th></tr></thead>
  <tbody>
    {missing_rows or '<tr><td colspan=\"5\">No one is missing according to schedule.</td></tr>'}
  </tbody>
</table>
"""


def emergency_response() -> AppResponse:
    return _html_response("Emergency Roll Call", _emergency_body())


def _firedrill_form_body() -> str:
    status = build_emergency_status()
    now = datetime.datetime.now()
    default_timestamp = now.strftime('%Y-%m-%dT%H:%M')
    missing_sections = []
    for person in status['missing']:
        field_name = _reason_field_name(person)
        options = ['<option value="">-- Select reason --</option>'] + [
            f"<option value=\"{html.escape(reason)}\">{html.escape(reason)}</option>"
            for reason in FIRE_DRILL_REASON_OPTIONS
        ]
        missing_sections.append(
            "<div class=\"mb-3\">"
            f"  <label class=\"form-label\" for=\"{field_name}\">"
            f"{html.escape(person.get('person_type', ''))} - {html.escape(person.get('name', ''))} ({html.escape(person.get('site', '')) or 'No site'})"
            "</label>"
            f"  <select class=\"form-select\" id=\"{field_name}\" name=\"{field_name}\" required>"
            f"    {' '.join(options)}"
            "  </select>"
            "</div>"
        )
    missing_html = ''.join(missing_sections) or '<p class="text-muted">All individuals accounted for.</p>'
    present_html = ''.join(
        [
            '<li class="list-group-item">'
            f"<strong>{html.escape(person.get('person_type', ''))}</strong>: {html.escape(person.get('name', ''))}"
            f" &mdash; {html.escape(person.get('site', ''))}"
            f" <span class=\"text-muted\">(since {html.escape(person.get('timestamp', ''))})</span>"
            '</li>'
            for person in status['present']
        ]
    ) or '<li class="list-group-item text-muted">No one is signed in.</li>'
    return f"""
<h2>Fire Drill Report</h2>
<p>Use this form to document the outcome of the most recent fire drill.</p>
<form method=\"post\" action=\"/firedrill_report\">
  <div class=\"row\">
    <div class=\"col-md-6\">
      <div class=\"mb-3\">
        <label class=\"form-label\" for=\"drill_datetime\">Fire drill date &amp; time</label>
        <input type=\"datetime-local\" class=\"form-control\" id=\"drill_datetime\" name=\"drill_datetime\" value=\"{default_timestamp}\" required>
      </div>
    </div>
    <div class=\"col-md-6\">
      <div class=\"mb-3\">
        <label class=\"form-label\" for=\"drill_location\">Location</label>
        <input type=\"text\" class=\"form-control\" id=\"drill_location\" name=\"location\" placeholder=\"e.g. Fort Wayne\" required>
      </div>
    </div>
  </div>
  <div class=\"mb-4\">
    <h3>Accounted For</h3>
    <ul class=\"list-group\">
      {present_html}
    </ul>
  </div>
  <div class=\"mb-4\">
    <h3>Not Accounted For</h3>
    {missing_html}
  </div>
  <button type=\"submit\" class=\"btn btn-primary\">Export Fire Drill Report</button>
</form>
"""


def firedrill_form_response() -> AppResponse:
    return _html_response("Fire Drill Report", _firedrill_form_body())


def _load_data_body() -> str:
    webhook_status = 'Configured' if SETTINGS.get('teams_webhook_url') else 'Not Configured'
    webhook_hint = (
        f"<span class=\"badge bg-success\">{webhook_status}</span>"
        if SETTINGS.get('teams_webhook_url')
        else f"<span class=\"badge bg-secondary\">{webhook_status}</span>"
    )
    return f"""
<h2>Load Data</h2>
<p>Use this page to upload CSV files for staff, clients, and schedules. The server will overwrite existing data in memory.</p>
<div class=\"row\">
  <div class=\"col-md-4\">
    <h4>Upload Staff CSV</h4>
    <form method=\"post\" action=\"/upload_csv\" enctype=\"multipart/form-data\">
      <input type=\"hidden\" name=\"category\" value=\"staff\">
      <div class=\"mb-3\">
        <input class=\"form-control\" type=\"file\" name=\"file\" accept=\".csv\" required>
      </div>
      <button type=\"submit\" class=\"btn btn-primary\">Upload Staff</button>
    </form>
  </div>
  <div class=\"col-md-4\">
    <h4>Upload Clients CSV</h4>
    <form method=\"post\" action=\"/upload_csv\" enctype=\"multipart/form-data\">
      <input type=\"hidden\" name=\"category\" value=\"clients\">
      <div class=\"mb-3\">
        <input class=\"form-control\" type=\"file\" name=\"file\" accept=\".csv\" required>
      </div>
      <button type=\"submit\" class=\"btn btn-primary\">Upload Clients</button>
    </form>
  </div>
  <div class=\"col-md-4\">
    <h4>Upload Schedule CSV</h4>
    <form method=\"post\" action=\"/upload_csv\" enctype=\"multipart/form-data\">
      <input type=\"hidden\" name=\"category\" value=\"schedule\">
      <div class=\"mb-3\">
        <input class=\"form-control\" type=\"file\" name=\"file\" accept=\".csv\" required>
      </div>
      <button type=\"submit\" class=\"btn btn-primary\">Upload Schedule</button>
    </form>
  </div>
</div>
<hr>
<div class=\"row\">
  <div class=\"col-md-6\">
    <h4>Microsoft Teams Emergency Notifications {webhook_hint}</h4>
    <p>Provide an incoming webhook URL from your Microsoft Teams channel to enable one-click emergency notifications.</p>
    <form method=\"post\" action=\"/configure_teams\">
      <div class=\"mb-3\">
        <label for=\"teams_webhook\" class=\"form-label\">Teams Webhook URL</label>
        <input type=\"url\" class=\"form-control\" id=\"teams_webhook\" name=\"webhook\" placeholder=\"https://...\" value=\"{SETTINGS.get('teams_webhook_url', '')}\" required>
      </div>
      <button type=\"submit\" class=\"btn btn-primary\">Save Webhook</button>
    </form>
    <p class=\"mt-2 text-muted\">The URL is stored on this server only and used when sending an emergency notification.</p>
  </div>
</div>
"""


def load_data_response() -> AppResponse:
    return _html_response("Load Data", _load_data_body())


def _sign_event_from_form(form: Mapping[str, str]) -> Optional[Dict[str, str]]:
    person_field = form.get('person')
    action_field = form.get('action')
    site_field = form.get('site')
    if not person_field or not action_field or not site_field:
        return None
    if '|' not in person_field:
        return None
    person_type, person_id = person_field.split('|', 1)
    person_type = person_type.strip().lower()
    person_id = person_id.strip()
    if person_type not in {'staff', 'client'}:
        return None
    records = DATA['staff'] if person_type == 'staff' else DATA['clients']
    person = records.get(person_id)
    if not person:
        return None
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    site = site_field.strip()
    if not site:
        return None
    action = action_field.strip().lower()
    if action not in {'sign_in', 'sign_out'}:
        return None
    event = {
        'person_type': person_type,
        'person_id': person_id,
        'name': person.get('name', ''),
        'site': site,
        'timestamp': timestamp,
        'action': action,
    }
    return event


def sign_action_response(form: Mapping[str, str]) -> AppResponse:
    event = _sign_event_from_form(form)
    if not event:
        body = '<p class="text-danger">Invalid submission.</p><a href="/" class="btn btn-secondary">Back to Home</a>'
        return _html_response('Error', body, HTTPStatus.BAD_REQUEST)
    recorded = _sign_in_service().record_action(
        person_type=event['person_type'],
        person_id=event['person_id'],
        action=event['action'],
        site=event['site'],
    )
    message = (
        f"Successfully recorded {event['action'].replace('_', ' ').title()} for {html.escape(event['name'])} at {recorded['timestamp']}"
    )
    body = (
        f'<div class="alert alert-success" role="alert">{message}</div><a href="/" class="btn btn-primary">Return to Home</a>'
    )
    return _html_response('Submission Received', body)


def upload_csv_response(form: cgi.FieldStorage) -> AppResponse:
    category = form.getvalue('category') if form else None
    fileitem = form['file'] if form and 'file' in form else None
    if (
        category not in ('staff', 'clients', 'schedule')
        or fileitem is None
        or getattr(fileitem, 'file', None) is None
    ):
        body = '<p class="text-danger">Invalid upload request.</p><a href="/load_data" class="btn btn-secondary">Back</a>'
        return _html_response('Error', body, HTTPStatus.BAD_REQUEST)
    upload_path = os.path.join(RUNTIME_DIR, f'tmp_upload_{category}.csv')
    with open(upload_path, 'wb') as fout:
        while True:
            chunk = fileitem.file.read(8192)
            if not chunk:
                break
            fout.write(chunk)
    try:
        if category in ('staff', 'clients'):
            load_csv(upload_path, category)
        else:
            load_schedule_csv(upload_path)
    except Exception as exc:
        body = f'<p class="text-danger">Error processing CSV: {html.escape(str(exc))}</p>'
        return _html_response('Upload Error', body, HTTPStatus.BAD_REQUEST)
    finally:
        try:
            os.remove(upload_path)
        except OSError:
            pass
    message = f'Successfully loaded {html.escape(category)} data.'
    body = f'<div class="alert alert-success" role="alert">{message}</div><a href="/load_data" class="btn btn-primary">Back to Load Data</a>'
    return _html_response('Upload Successful', body)


def configure_teams_response(form: Mapping[str, str]) -> AppResponse:
    webhook = form.get('webhook', '').strip()
    if not webhook:
        body = '<p class="text-danger">No webhook URL provided.</p><a href="/load_data" class="btn btn-secondary">Back</a>'
        return _html_response('Teams Configuration Error', body, HTTPStatus.BAD_REQUEST)
    if not webhook.lower().startswith('https://'):
        body = '<p class="text-danger">Webhook URLs must start with https://</p><a href="/load_data" class="btn btn-secondary">Back</a>'
        return _html_response('Teams Configuration Error', body, HTTPStatus.BAD_REQUEST)
    SETTINGS['teams_webhook_url'] = webhook
    save_settings()
    body = '<div class="alert alert-success" role="alert">Microsoft Teams webhook saved.</div><a href="/load_data" class="btn btn-primary">Back to Load Data</a>'
    return _html_response('Teams Configuration Saved', body)


def notify_teams_response() -> AppResponse:
    webhook = SETTINGS.get('teams_webhook_url', '').strip()
    if not webhook:
        body = '<p class="text-danger">No Microsoft Teams webhook configured.</p><a href="/emergency" class="btn btn-secondary">Back</a>'
        return _html_response('Notification Error', body, HTTPStatus.BAD_REQUEST)
    status = build_emergency_status()
    success, message = send_teams_notification(webhook, status)
    if not success:
        body = f'<p class="text-danger">{html.escape(message)}</p><a href="/emergency" class="btn btn-secondary">Back to Emergency</a>'
        return _html_response('Notification Error', body, HTTPStatus.BAD_REQUEST)
    body = f'<div class="alert alert-success" role="alert">{html.escape(message)}</div><a href="/emergency" class="btn btn-primary">Back to Emergency</a>'
    return _html_response('Notification Sent', body)


def firedrill_submission_response(form: Mapping[str, str]) -> AppResponse:
    status = build_emergency_status()
    location = form.get('location', '').strip()
    drill_dt_raw = form.get('drill_datetime', '').strip()
    if not location or not drill_dt_raw:
        body = '<p class="text-danger">Fire drill date/time and location are required.</p><a href="/firedrill_report" class="btn btn-secondary">Back</a>'
        return _html_response('Fire Drill Report Error', body, HTTPStatus.BAD_REQUEST)
    try:
        drill_dt = datetime.datetime.fromisoformat(drill_dt_raw)
    except ValueError:
        body = '<p class="text-danger">Invalid date/time provided.</p><a href="/firedrill_report" class="btn btn-secondary">Back</a>'
        return _html_response('Fire Drill Report Error', body, HTTPStatus.BAD_REQUEST)
    reasons = {}
    for person in status['missing']:
        field = _reason_field_name(person)
        reason = form.get(field, '').strip()
        if status['missing'] and not reason:
            body = '<p class="text-danger">Please select a reason for each individual who was not accounted for.</p><a href="/firedrill_report" class="btn btn-secondary">Back</a>'
            return _html_response('Fire Drill Report Error', body, HTTPStatus.BAD_REQUEST)
        reasons[(person.get('person_type'), person.get('person_id'))] = reason
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Fire Drill Report'])
    writer.writerow(['Generated At', datetime.datetime.now().isoformat(timespec='seconds')])
    writer.writerow(['Fire Drill Date/Time', drill_dt.isoformat(timespec='minutes')])
    writer.writerow(['Location', location])
    writer.writerow([])
    writer.writerow(['Person Type', 'Name', 'Site', 'Status', 'Details'])
    for person in status['present']:
        details = person.get('timestamp', '')
        detail_text = f"Signed in at {details}" if details else ''
        writer.writerow([
            person.get('person_type', ''),
            person.get('name', ''),
            person.get('site', ''),
            'Accounted For',
            detail_text,
        ])
    for person in status['missing']:
        key = (person.get('person_type'), person.get('person_id'))
        reason = reasons.get(key, 'Reason not provided')
        writer.writerow([
            person.get('person_type', ''),
            person.get('name', ''),
            person.get('site', ''),
            'Not Accounted For',
            reason,
        ])
    csv_data = output.getvalue().encode('utf-8')
    safe_location = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in location.strip()) or 'location'
    timestamp_component = drill_dt.strftime('%Y%m%d-%H%M')
    filename = f"firedrill_{timestamp_component}_{safe_location}.csv"
    headers = {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Content-Length': str(len(csv_data)),
    }
    return AppResponse(status=HTTPStatus.OK, headers=headers, body=csv_data)


def static_file_response(path: str) -> AppResponse:
    file_path = os.path.join(BASE_DIR, path.lstrip('/'))
    if not os.path.isfile(file_path):
        return _text_response('File not found', HTTPStatus.NOT_FOUND)
    with open(file_path, 'rb') as handle:
        content = handle.read()
    content_type = 'text/css' if file_path.endswith('.css') else 'application/octet-stream'
    headers = {'Content-Type': content_type, 'Content-Length': str(len(content))}
    return AppResponse(status=HTTPStatus.OK, headers=headers, body=content)


class AppRouter:
    """Route HTTP requests to the appropriate handler functions."""

    def handle(self, method: str, raw_path: str, headers: Mapping[str, str], body: bytes) -> AppResponse:
        parsed = urlparse(raw_path)
        path = parsed.path or '/'
        method = (method or 'GET').upper()
        if method == 'GET':
            if path == '/':
                return home_response()
            if path == '/admin':
                return admin_response()
            if path == '/emergency':
                return emergency_response()
            if path == '/firedrill_report':
                return firedrill_form_response()
            if path == '/load_data':
                return load_data_response()
            if path.startswith('/static/'):
                return static_file_response(path)
            return _text_response('Not found', HTTPStatus.NOT_FOUND)
        if method == 'POST':
            if path == '/sign_action':
                form = _parse_urlencoded(body)
                return sign_action_response(form)
            if path == '/configure_teams':
                form = _parse_urlencoded(body)
                return configure_teams_response(form)
            if path == '/notify_teams':
                return notify_teams_response()
            if path == '/firedrill_report':
                form = _parse_urlencoded(body)
                return firedrill_submission_response(form)
            if path == '/upload_csv':
                form = _parse_multipart_form(headers, body)
                return upload_csv_response(form)
            return _text_response('Not found', HTTPStatus.NOT_FOUND)
        if method == 'HEAD':
            # Reuse GET logic but clear body to comply with HEAD semantics.
            get_response = self.handle('GET', raw_path, headers, body)
            return AppResponse(status=get_response.status, headers=get_response.headers, body=b'')
        return _text_response('Method not allowed', HTTPStatus.METHOD_NOT_ALLOWED)


ROUTER = AppRouter()


def _snapshot_store() -> RuntimeSnapshotStore:
    return RuntimeSnapshotStore(RUNTIME_DIR)


def _settings_store() -> SettingsStore:
    return SettingsStore(RUNTIME_DIR)


def _audit_logger() -> AuditLogger:
    return AuditLogger(RUNTIME_DIR)


def _sign_in_service() -> SignInService:
    return SignInService(DATA, _snapshot_store(), _audit_logger(), APP_CONFIG)


def _notification_service() -> EmergencyNotificationService:
    return EmergencyNotificationService(APP_CONFIG)


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
    DATA_LOADER.load_people(file_path, category)


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
    DATA_LOADER.load_schedule(file_path)


def save_runtime_state() -> None:
    """Save the current sign‑in records to disk as JSON.

    This allows the state to be preserved across server restarts. Only
    sign‑in records are stored in the runtime snapshot because staff,
    client, and schedule data are typically loaded from CSV files.
    """
    _snapshot_store().save(DATA['signins'])


def load_runtime_state() -> None:
    """Load sign‑in records from disk if they exist."""
    DATA['signins'] = _snapshot_store().load()


def save_settings() -> None:
    """Persist runtime settings such as webhook URLs."""
    try:
        _settings_store().save(SETTINGS)
    except OSError:
        # Failing to persist settings should not crash the app; configuration can
        # simply be re-entered if the write fails.
        pass


def load_settings() -> None:
    """Load runtime settings from disk if available."""
    data = _settings_store().load()
    webhook = data.get('teams_webhook_url', '')
    if isinstance(webhook, str):
        SETTINGS['teams_webhook_url'] = webhook


def build_emergency_status():
    """Compile lists of present and missing individuals for today's schedule."""
    return REPORTING_SERVICE.build_emergency_status()


def format_emergency_markdown(status):
    """Return a Markdown string summarising the emergency roll-call status."""

    lines = [
        f"**Emergency Roll Call - {status['date']}**",
        f"Present: {len(status['present'])}",
        f"Missing: {len(status['missing'])}",
        '',
    ]

    if status['present']:
        lines.append('**Present**')
        for person in status['present']:
            timestamp = person.get('timestamp', '')
            if timestamp:
                lines.append(
                    f"- {person.get('person_type', '')}: {person.get('name', '')} @ {person.get('site', '')} (since {timestamp})"
                )
            else:
                lines.append(
                    f"- {person.get('person_type', '')}: {person.get('name', '')} @ {person.get('site', '')}"
                )
        lines.append('')

    if status['missing']:
        lines.append('**Missing Individuals**')
        for person in status['missing']:
            contact_details = ', '.join(
                filter(None, [person.get('contact_name', ''), person.get('contact_phone', '')])
            )
            if contact_details:
                lines.append(
                    f"- {person.get('person_type', '')}: {person.get('name', '')} (Site: {person.get('site', '')}; Contact: {contact_details})"
                )
            else:
                lines.append(
                    f"- {person.get('person_type', '')}: {person.get('name', '')} (Site: {person.get('site', '')})"
                )
        lines.append('')
    else:
        lines.append('All scheduled individuals are accounted for.')
        lines.append('')

    lines.append('Please respond in Teams with your status and confirm the safety of your staff and clients.')
    return '\n'.join(lines)


def send_teams_notification(webhook, status):
    """Send the emergency status to the Microsoft Teams webhook.

    Returns a tuple ``(success, message)`` where ``success`` is ``True`` if the
    message was delivered and ``False`` otherwise. ``message`` contains details
    suitable for displaying to the end user.
    """

    markdown = format_emergency_markdown(status)
    return _notification_service().send(webhook, markdown)


class SignInHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler that delegates routing to the shared app router."""

    server_version = "ABASignIn/1.0"

    def _send_app_response(self, response: AppResponse) -> None:
        status_code = response.status.value if isinstance(response.status, HTTPStatus) else int(response.status)
        self.send_response(status_code)
        for key, value in response.headers.items():
            self.send_header(str(key), str(value))
        self.end_headers()
        if self.command != 'HEAD' and response.body:
            self.wfile.write(response.body)

    def do_GET(self) -> None:
        response = ROUTER.handle('GET', self.path, self.headers, b'')
        self._send_app_response(response)

    def do_POST(self) -> None:
        length = int(self.headers.get('Content-Length', '0') or 0)
        body = self.rfile.read(length) if length else b''
        response = ROUTER.handle('POST', self.path, self.headers, body)
        self._send_app_response(response)

    def do_HEAD(self) -> None:  # pragma: no cover - simple delegation
        response = ROUTER.handle('HEAD', self.path, self.headers, b'')
        self._send_app_response(response)

    def log_message(self, format: str, *args) -> None:  # pragma: no cover - silence default logging
        pass

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
    load_settings()
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
