# ABA Sign‑In App

This repository contains a simple sign‑in web application tailored for
Applied Behaviour Analysis (ABA) providers. It was designed as a
minimal proof‑of‑concept to demonstrate how therapists, clients and
administrative staff can manage attendance, schedules and emergency
roll‑call information without relying on external services or
complicated infrastructure.

## Key Features

* **CSV Data Loading** – Administrators can upload CSV files for
  staff, clients and schedules via a web interface. See the
  `data/` folder for examples of the required column headers. Data is
  stored in memory and can be refreshed at any time.
* **Sign In/Out** – A unified home page allows staff and clients to
  select their name, choose the desired action (sign in or sign out),
  and specify the site they are attending. Each sign‑in/out action is
  timestamped.
* **Admin Dashboard** – The dashboard compares today’s schedule
  against the latest sign‑in events to highlight who is present and
  who is absent. It also shows the most recent 20 sign‑in actions.
* **Emergency Roll‑Call** – A dedicated page lists everyone
  scheduled for the current day, separating those who have signed in
  from those who are missing. For individuals who have not yet
  arrived, the page provides the contact details of their designated
  contact person (such as a supervisor or guardian) so the
  administrator can follow up quickly.
* **Self‑contained** – The application runs on Python’s standard
  library only (no third‑party packages). State is maintained in
  memory but snapshots of sign‑in history are written to `runtime/` so
  they survive a server restart.

## Getting Started

1. **Install Python** – Ensure you have Python 3.8+ installed on your
   machine. No additional packages are required.

2. **Clone or download the code** – Copy the `aba_sign_in_app`
   directory to a location on your server or workstation.

3. **Prepare your CSV files** – Use the following templates as a
   guide when creating your own files:

   * **staff.csv** – columns: `id`, `name`, `email`, `phone`, `site`,
     `contact_name`, `contact_phone`.
   * **clients.csv** – columns: `id`, `name`, `contact_name`,
     `contact_phone`, `site`.
   * **schedule.csv** – columns: `person_type` (`staff` or `client`),
     `id`, `date` (`YYYY‑MM‑DD`), `start_time` (`HH:MM` 24‑hour
     format), `end_time`, `site`.

   Place these files in the `data/` folder or upload them via the
   **Load Data** page once the server is running.

4. **Run the development server** – From a terminal in the
   `aba_sign_in_app` directory, execute:

   ```bash
   python3 app.py
   ```

   The server will start on port 8000 by default and prints a message
   such as `Server starting on http://localhost:8000 ...` when it is
   ready. You can stop it with `Ctrl+C`. To bind to another port, edit
   the `run_server()` call at the bottom of `app.py` or run the module
   directly with a custom port, e.g. `python3 -m app 8080`.

5. **Access the app** – Open a web browser and navigate to
   `http://localhost:8000`. Use the navigation bar to sign in
   individuals, load data, view the admin dashboard, or check the
   emergency roll‑call list.

## Microsoft Teams emergency notifications

The application can post an emergency roll call summary to a Microsoft
Teams channel via an incoming webhook.

1. **Create an incoming webhook in Teams.** Follow the Microsoft Teams
   documentation to add the *Incoming Webhook* connector to the channel
   you want to notify. Copy the HTTPS URL that Teams generates.
2. **Configure the webhook in the app.** Open the **Load Data** page
   and paste the URL into the *Teams Webhook URL* field. The value is
   stored in `runtime/settings.json` so it persists across restarts.
3. **Preview the message.** Visit the **Emergency** page. When a
   webhook is configured, the page shows a live Markdown preview of the
   payload that will be posted to Teams, including everyone marked as
   present or missing.
4. **Send the alert.** Click the *Send Teams Emergency Notification*
   button. The server will format the current roll call status and
   perform an HTTP `POST` to the webhook URL.
5. **Verify delivery in Teams.** A successful call returns HTTP 200 or
   202 from Microsoft. Any non-success response (for example, network
   restrictions that return 403) is reported back to the UI so you can
   retry from an environment with outbound access.

Encourage staff to acknowledge the alert directly in Teams so that the
channel thread becomes a quick headcount for both staff and their
assigned clients.

## Extending the App

This is a barebones example meant for demonstration and educational
purposes. For a production‑ready system you would want to:

* Use a proper web framework (e.g. Flask or Django) with session
  management and authentication.
* Store data in a relational database or secure cloud service rather
  than in memory.
* Integrate automated notifications (SMS, email, push) for absence
  alerts or emergency announcements.
* Provide secure user logins for staff, therapists and parents.
* Include HIPAA‑compliant data privacy measures and audit logging.

Feel free to adapt and build on this foundation to meet the specific
needs of your organisation.
