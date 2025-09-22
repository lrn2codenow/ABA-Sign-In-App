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

4. **Run the server** – From a terminal in the `aba_sign_in_app`
   directory, execute:

   ```bash
   python3 app.py
   ```

   The server will start on port 8000 by default. You can specify a
   different port by editing the call to `run_server()` at the bottom
   of `app.py`.

5. **Access the app** – Open a web browser and navigate to
   `http://localhost:8000`. Use the navigation bar to sign in
   individuals, load data, view the admin dashboard, or check the
   emergency roll‑call list.

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