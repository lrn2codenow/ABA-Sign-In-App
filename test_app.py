"""Comprehensive integration and unit tests for the ABA sign-in app."""

import datetime
import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error

import app


class SignInServerTestCase(unittest.TestCase):
    """Exercise the public functionality exposed by the HTTP server."""

    @classmethod
    def setUpClass(cls):
        # Use a temporary runtime directory so tests do not affect repo state.
        cls._runtime_dir = tempfile.mkdtemp(prefix="aba_runtime_")
        app.RUNTIME_DIR = cls._runtime_dir
        os.makedirs(app.RUNTIME_DIR, exist_ok=True)

    def setUp(self):
        # Reset all in-memory data before each test to avoid state leakage.
        app.DATA['staff'] = {}
        app.DATA['clients'] = {}
        app.DATA['schedule'] = []
        app.DATA['signins'] = []
        app.SETTINGS['teams_webhook_url'] = ''
        app.SETTINGS['locations'] = []
        app.ASSIGNMENTS['staff'] = {}
        app.ASSIGNMENTS['clients'] = {}
        self.server = None
        self.server_thread = None
        self.port = None
        self.today = datetime.date.today().isoformat()
        snapshot_path = os.path.join(app.RUNTIME_DIR, 'signins.json')
        if os.path.exists(snapshot_path):
            os.remove(snapshot_path)
        assignments_path = os.path.join(app.RUNTIME_DIR, 'assignments.json')
        if os.path.exists(assignments_path):
            os.remove(assignments_path)
        fire_dir = os.path.join(app.RUNTIME_DIR, 'fire_drills')
        if os.path.isdir(fire_dir):
            shutil.rmtree(fire_dir)

    def tearDown(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.server_thread is not None:
            self.server_thread.join(timeout=5)

    # Helper utilities -------------------------------------------------
    def _populate_sample_data(self):
        app.DATA['staff'] = {
            's1': {
                'id': 's1',
                'name': 'Alice Therapist',
                'email': 'alice@example.com',
                'phone': '555-0100',
                'site': 'Fort Wayne',
                'contact_name': 'Supervisor Sue',
                'contact_phone': '555-0101',
            },
        }
        app.DATA['clients'] = {
            'c1': {
                'id': 'c1',
                'name': 'Bobby Learner',
                'contact_name': 'Parent Patty',
                'contact_phone': '555-0201',
                'site': 'Fort Wayne',
            },
            'c2': {
                'id': 'c2',
                'name': 'Charlie Learner',
                'contact_name': 'Parent Paul',
                'contact_phone': '555-0202',
                'site': 'Fort Wayne',
            },
        }
        app.DATA['schedule'] = [
            {
                'person_type': 'staff',
                'id': 's1',
                'date': self.today,
                'start_time': '09:00',
                'end_time': '17:00',
                'site': 'Fort Wayne',
            },
            {
                'person_type': 'client',
                'id': 'c1',
                'date': self.today,
                'start_time': '09:00',
                'end_time': '11:00',
                'site': 'Fort Wayne',
            },
            {
                'person_type': 'client',
                'id': 'c2',
                'date': self.today,
                'start_time': '10:00',
                'end_time': '12:00',
                'site': 'Fort Wayne',
            },
        ]

    def _start_server(self):
        self.server = app.HTTPServer(('localhost', 0), app.SignInHTTPRequestHandler)
        self.port = self.server.server_address[1]
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def _request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('localhost', self.port)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, response.getheader('Content-Type'), data

    # Unit tests -------------------------------------------------------
    def test_load_csv_parses_staff_and_clients(self):
        staff_csv = "id,Name,Email,Phone,Site,Contact_Name,Contact_Phone\n" \
            "s2,Donna Therapist,don@example.com,555-0300,Chicago,Supervisor Sid,555-0301\n"
        clients_csv = "ID,Name,Contact_Name,Contact_Phone,Site\n" \
            "c3,Eddie Learner,Caregiver Cara,555-0400,Chicago\n"
        with tempfile.NamedTemporaryFile('w+', delete=False, newline='') as staff_file:
            staff_file.write(staff_csv)
            staff_path = staff_file.name
        with tempfile.NamedTemporaryFile('w+', delete=False, newline='') as client_file:
            client_file.write(clients_csv)
            client_path = client_file.name
        try:
            app.load_csv(staff_path, 'staff')
            app.load_csv(client_path, 'clients')
        finally:
            os.remove(staff_path)
            os.remove(client_path)

        self.assertIn('s2', app.DATA['staff'])
        self.assertEqual(app.DATA['staff']['s2']['name'], 'Donna Therapist')
        self.assertIn('c3', app.DATA['clients'])
        self.assertEqual(app.DATA['clients']['c3']['contact_phone'], '555-0400')

    def test_load_schedule_csv_validates_rows(self):
        csv_contents = """person_type,id,date,start_time,end_time,site
staff,s1,2030-01-01,09:00,17:00,Fort Wayne
client,,2030-01-01,09:00,10:00,Fort Wayne
coach,s2,2030-01-01,09:00,10:00,Fort Wayne
client,c4,invalid,09:00,11:00,Fort Wayne
"""
        with tempfile.NamedTemporaryFile('w+', delete=False, newline='') as schedule_file:
            schedule_file.write(csv_contents)
            schedule_path = schedule_file.name
        try:
            app.load_schedule_csv(schedule_path)
        finally:
            os.remove(schedule_path)

        self.assertEqual(len(app.DATA['schedule']), 1)
        self.assertEqual(app.DATA['schedule'][0]['id'], 's1')

    # Integration tests ------------------------------------------------
    def test_sign_in_flow_updates_history_and_dashboard(self):
        self._populate_sample_data()
        self._start_server()

        # Submit a staff sign-in via form encoded POST.
        body = 'person=staff%7Cs1&action=sign_in&site=Fort+Wayne'
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        status, content_type, payload = self._request('POST', '/sign_action', body, headers)
        self.assertEqual(status, 200)
        html = payload.decode('utf-8')
        self.assertIn('Successfully recorded Sign In for Alice Therapist', html)
        self.assertEqual(app.DATA['signins'][-1]['action'], 'sign_in')

        # Runtime snapshot should be written and reloadable.
        snapshot_path = os.path.join(app.RUNTIME_DIR, 'signins.json')
        self.assertTrue(os.path.exists(snapshot_path))
        with open(snapshot_path, 'r', encoding='utf-8') as fh:
            saved = json.load(fh)
        self.assertEqual(saved[-1]['name'], 'Alice Therapist')

        # Clear sign-ins and load from runtime snapshot.
        app.DATA['signins'] = []
        app.load_runtime_state()
        self.assertEqual(app.DATA['signins'][-1]['name'], 'Alice Therapist')

        # Admin dashboard should show staff as present.
        status, _, payload = self._request('GET', '/admin')
        self.assertEqual(status, 200)
        admin_html = payload.decode('utf-8')
        self.assertIn('Alice Therapist', admin_html)
        self.assertIn('Present', admin_html)

        # Now sign the staff member out and confirm dashboard updates.
        body = 'person=staff%7Cs1&action=sign_out&site=Fort+Wayne'
        status, _, _ = self._request('POST', '/sign_action', body, headers)
        self.assertEqual(status, 200)
        status, _, payload = self._request('GET', '/admin')
        self.assertEqual(status, 200)
        admin_html = payload.decode('utf-8')
        self.assertIn('Absent', admin_html)

    def test_emergency_page_lists_present_and_missing(self):
        self._populate_sample_data()
        # Mark one staff and one client as present; leave second client absent.
        now = datetime.datetime.now().isoformat(timespec='seconds')
        app.DATA['signins'] = [
            {
                'person_type': 'staff',
                'id': 's1',
                'name': 'Alice Therapist',
                'site': 'Fort Wayne',
                'timestamp': now,
                'action': 'sign_in',
            },
            {
                'person_type': 'client',
                'id': 'c1',
                'name': 'Bobby Learner',
                'site': 'Fort Wayne',
                'timestamp': now,
                'action': 'sign_in',
            },
        ]
        self._start_server()

        status, _, payload = self._request('GET', '/emergency')
        self.assertEqual(status, 200)
        html = payload.decode('utf-8')
        self.assertIn('Alice Therapist', html)
        self.assertIn('Bobby Learner', html)
        # Missing client (c2) should list contact information.
        self.assertIn('Charlie Learner', html)
        self.assertIn('Parent Paul', html)
        self.assertIn('Complete Fire Drill Report', html)

    def test_emergency_page_preview_when_webhook_configured(self):
        self._populate_sample_data()
        app.SETTINGS['teams_webhook_url'] = 'https://example.com/webhook'
        app.DATA['signins'] = [
            {
                'person_type': 'staff',
                'id': 's1',
                'name': 'Alice Therapist',
                'site': 'Fort Wayne',
                'timestamp': '09:00',
                'action': 'sign_in',
            }
        ]
        self._start_server()

        status, _, payload = self._request('GET', '/emergency')
        self.assertEqual(status, 200)
        html = payload.decode('utf-8')
        self.assertIn('Preview Teams message', html)
        self.assertIn('Alice Therapist', html)

    def test_format_emergency_markdown_includes_present_and_missing(self):
        status = {
            'date': '2030-01-01',
            'present': [
                {
                    'person_type': 'Staff',
                    'person_id': 's1',
                    'name': 'Alice',
                    'site': 'Fort Wayne',
                    'timestamp': '09:00',
                }
            ],
            'missing': [
                {
                    'person_type': 'Client',
                    'person_id': 'c1',
                    'name': 'Bobby',
                    'site': 'Fort Wayne',
                    'contact_name': 'Parent Patty',
                    'contact_phone': '555-0101',
                }
            ],
        }
        markdown = app.format_emergency_markdown(status)
        self.assertIn('**Emergency Roll Call - 2030-01-01**', markdown)
        self.assertIn('- Staff: Alice @ Fort Wayne (since 09:00)', markdown)
        self.assertIn('- Client: Bobby (Site: Fort Wayne; Contact: Parent Patty, 555-0101)', markdown)

    def test_send_teams_notification_handles_errors(self):
        status = {
            'date': '2030-01-01',
            'present': [],
            'missing': [],
        }
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('network down')):
            success, message = app.send_teams_notification('https://example.com/webhook', status)
        self.assertFalse(success)
        self.assertIn('Failed to send notification', message)

    def test_notify_endpoint_uses_helper(self):
        self._populate_sample_data()
        app.SETTINGS['teams_webhook_url'] = 'https://example.com/webhook'
        self._start_server()

        with mock.patch('app.send_teams_notification', return_value=(True, 'ok')) as mocked:
            status, _, payload = self._request('POST', '/notify_teams')
        self.assertEqual(status, 200)
        mocked.assert_called_once()
        self.assertIn('Notification Sent', payload.decode('utf-8'))

    def test_upload_csv_replaces_data(self):
        self._populate_sample_data()
        self._start_server()

        boundary = '----WebKitFormBoundaryTEST'
        new_staff_csv = (
            'id,name,email,phone,site,contact_name,contact_phone\n'
            's9,Zelda Therapist,zelda@example.com,555-0900,Chicago,Supervisor Sam,555-0901\n'
        )
        multipart_body = (
            f'--{boundary}\r\n'
            'Content-Disposition: form-data; name="category"\r\n\r\n'
            'staff\r\n'
            f'--{boundary}\r\n'
            'Content-Disposition: form-data; name="file"; filename="staff.csv"\r\n'
            'Content-Type: text/csv\r\n\r\n'
            f'{new_staff_csv}\r\n'
            f'--{boundary}--\r\n'
        )
        headers = {'Content-Type': f'multipart/form-data; boundary={boundary}'}
        status, _, payload = self._request('POST', '/upload_csv', multipart_body.encode('utf-8'), headers)
        self.assertEqual(status, 200)
        html = payload.decode('utf-8')
        self.assertIn('Successfully loaded staff data', html)
        self.assertIn('s9', app.DATA['staff'])
        self.assertEqual(app.DATA['staff']['s9']['name'], 'Zelda Therapist')

    def test_firedrill_report_form_shows_reason_dropdowns(self):
        self._populate_sample_data()
        # Mark staff as present so at least one accounted for entry exists.
        now = datetime.datetime.now().isoformat(timespec='seconds')
        app.DATA['signins'] = [
            {
                'person_type': 'staff',
                'id': 's1',
                'name': 'Alice Therapist',
                'site': 'Fort Wayne',
                'timestamp': now,
                'action': 'sign_in',
            }
        ]
        self._start_server()

        status_code, content_type, payload = self._request('GET', '/firedrill_report')
        self.assertEqual(status_code, 200)
        self.assertIn('text/html', content_type)
        html = payload.decode('utf-8')
        self.assertIn('Fire Drill Report', html)
        self.assertIn('reason_client_c2', html)
        for option in app.FIRE_DRILL_REASON_OPTIONS:
            self.assertIn(option, html)

    def test_firedrill_report_submission_downloads_csv(self):
        self._populate_sample_data()
        now = datetime.datetime(2030, 1, 1, 9, 0).isoformat(timespec='seconds')
        app.DATA['signins'] = [
            {
                'person_type': 'staff',
                'id': 's1',
                'name': 'Alice Therapist',
                'site': 'Fort Wayne',
                'timestamp': now,
                'action': 'sign_in',
            }
        ]
        self._start_server()

        body = (
            'drill_datetime=2030-01-01T10%3A00'
            '&location=Fort+Wayne+Center'
            '&reason_client_c1=Sick%2FCalled+off'
            '&reason_client_c2=On+community+outing'
        )
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        status_code, content_type, payload = self._request('POST', '/firedrill_report', body, headers)
        self.assertEqual(status_code, 200)
        self.assertIn('text/csv', content_type)
        csv_text = payload.decode('utf-8')
        self.assertIn('Fire Drill Date/Time,2030-01-01T10:00', csv_text)
        self.assertIn('Fort Wayne Center', csv_text)
        self.assertIn('Accounted For', csv_text)
        self.assertIn('Not Accounted For', csv_text)
        self.assertIn('Sick/Called off', csv_text)
        self.assertIn('On community outing', csv_text)


if __name__ == '__main__':
    unittest.main()
