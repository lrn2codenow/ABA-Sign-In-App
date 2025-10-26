# ABA Sign-In App - Pilot Quick Start Guide

**For**: Technical Administrators
**Pilot Scale**: 60 Staff + 60 Clients = 120 Users
**Time to Deploy**: 2-3 days for basic setup

This quick start guide provides the essential steps to get the pilot running. For complete details, see PILOT_PLAN.md.

---

## Pre-Flight Checklist

### Week Before Pilot

#### 1. Server Setup (2-3 hours)

**Option A: Quick Cloud Deployment (Recommended)**

```bash
# Launch AWS EC2 instance or equivalent
# - Ubuntu 22.04 LTS
# - t3.small (2 vCPU, 2GB RAM)
# - Open ports 22, 80, 443

# SSH into server
ssh ubuntu@your-server-ip

# Install dependencies
sudo apt update
sudo apt install -y python3 python3-pip nginx certbot python-certbot-nginx

# Clone repository
cd /opt
sudo git clone https://github.com/yourusername/ABA-Sign-In-App.git
cd ABA-Sign-In-App

# Set up runtime directory
sudo mkdir -p runtime
sudo chmod 755 runtime

# Set environment variables
cat > /opt/ABA-Sign-In-App/.env <<EOF
export ABA_RUNTIME_DIR=/opt/ABA-Sign-In-App/runtime
export ABA_ENVIRONMENT=pilot
export ABA_TIMEZONE=America/Indiana/Indianapolis
export ABA_DATA_RETENTION_DAYS=90
export ABA_AUDIT_LOG_ENABLED=true
export ABA_LOG_LEVEL=INFO
EOF

# Test the app
source .env
python3 app.py
# Visit http://your-server-ip:8000 to verify it works
# Press Ctrl+C to stop
```

**Option B: Local Development (Testing Only)**

```bash
# On your laptop/workstation
git clone https://github.com/yourusername/ABA-Sign-In-App.git
cd ABA-Sign-In-App
python3 app.py
# Visit http://localhost:8000
```

#### 2. Set Up Systemd Service (Production)

```bash
# Create service file
sudo nano /etc/systemd/system/aba-signin.service
```

Paste this content:
```ini
[Unit]
Description=ABA Sign-In Application
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/ABA-Sign-In-App
EnvironmentFile=/opt/ABA-Sign-In-App/.env
ExecStart=/usr/bin/python3 /opt/ABA-Sign-In-App/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable aba-signin.service
sudo systemctl start aba-signin.service
sudo systemctl status aba-signin.service  # Should show "active (running)"
```

#### 3. Configure Nginx and HTTPS (15 minutes)

```bash
# Create Nginx config
sudo nano /etc/nginx/sites-available/aba-signin
```

Paste this content (replace `your-domain.com`):
```nginx
server {
    listen 80;
    server_name signin.youraba.com;  # Replace with your domain

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site and get SSL certificate:
```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/aba-signin /etc/nginx/sites-enabled/
sudo nginx -t  # Test configuration
sudo systemctl reload nginx

# Get free SSL certificate
sudo certbot --nginx -d signin.youraba.com
# Follow prompts, select redirect HTTP to HTTPS
```

Now visit: **https://signin.youraba.com**

#### 4. Set Up Daily Backups (10 minutes)

```bash
# Create backup script
sudo nano /opt/ABA-Sign-In-App/backup.sh
```

Paste this content:
```bash
#!/bin/bash
BACKUP_DIR="/opt/aba-backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Backup runtime directory
tar -czf $BACKUP_DIR/runtime_$TIMESTAMP.tar.gz /opt/ABA-Sign-In-App/runtime/

# Keep only last 30 days
find $BACKUP_DIR -name "runtime_*.tar.gz" -mtime +30 -delete

echo "Backup completed: runtime_$TIMESTAMP.tar.gz"
```

Make executable and schedule:
```bash
sudo chmod +x /opt/ABA-Sign-In-App/backup.sh

# Add to crontab (runs daily at 2 AM)
sudo crontab -e
# Add this line:
0 2 * * * /opt/ABA-Sign-In-App/backup.sh >> /var/log/aba-backup.log 2>&1
```

### Data Preparation (1-2 days)

#### 5. Create CSV Files

**Template Downloads**: Use these Google Sheets templates or create in Excel

**A. staff.csv** (60 rows)
```csv
id,name,email,phone,site,contact_name,contact_phone
STF001,Jane Smith,jane.smith@aba.com,555-123-4567,Fort Wayne Main,Dr. Sarah Johnson,555-999-0001
STF002,John Doe,john.doe@aba.com,555-123-4568,Fort Wayne Main,Dr. Sarah Johnson,555-999-0001
STF003,Emily Davis,emily.davis@aba.com,555-123-4569,Fort Wayne Main,Dr. Sarah Johnson,555-999-0001
```

**Checklist**:
- [ ] Get staff roster from HR
- [ ] Assign unique IDs (STF001-STF060)
- [ ] Verify all contact information
- [ ] Identify supervisor for each staff member
- [ ] Use consistent site name throughout
- [ ] Export as CSV (UTF-8 encoding)

**B. clients.csv** (60 rows)
```csv
id,name,contact_name,contact_phone,site
CLT001,Charlie Brown,Mary Brown (Mother),555-234-5678,Fort Wayne Main
CLT002,Lucy Van Pelt,Richard Van Pelt (Father),555-234-5679,Fort Wayne Main
CLT003,Linus Van Pelt,Richard Van Pelt (Father),555-234-5679,Fort Wayne Main
```

**Checklist**:
- [ ] Get client roster
- [ ] Assign unique IDs (CLT001-CLT060)
- [ ] Get parent/guardian consent for contact info
- [ ] Verify guardian phone numbers
- [ ] Include relationship in contact name
- [ ] Export as CSV

**C. schedule.csv** (Estimate: 2,400 rows for 4 weeks)

Generate using spreadsheet formulas or Python script:
```csv
person_type,id,date,start_time,end_time,site
staff,STF001,2025-11-01,08:00,17:00,Fort Wayne Main
staff,STF001,2025-11-04,08:00,17:00,Fort Wayne Main
staff,STF001,2025-11-05,08:00,17:00,Fort Wayne Main
client,CLT001,2025-11-01,09:00,15:00,Fort Wayne Main
client,CLT001,2025-11-04,09:00,15:00,Fort Wayne Main
```

**Tips for Schedule Generation**:
- Use formulas to repeat weekly schedules
- Account for part-time staff/clients
- Exclude weekends and holidays
- Use YYYY-MM-DD for dates
- Use HH:MM 24-hour format for times
- Test with small sample first (1 week, 10 people)

**Python Helper Script** (optional):
```python
# generate_schedule.py
import csv
from datetime import datetime, timedelta

# Configuration
start_date = datetime(2025, 11, 1)  # Pilot start
num_weeks = 4
staff_ids = [f"STF{i:03d}" for i in range(1, 61)]
client_ids = [f"CLT{i:03d}" for i in range(1, 61)]
site = "Fort Wayne Main"

schedule = []

for week in range(num_weeks):
    for day in range(5):  # Monday-Friday
        current_date = start_date + timedelta(weeks=week, days=day)
        date_str = current_date.strftime("%Y-%m-%d")

        # Staff schedule (full-time: M-F, 8-5)
        for staff_id in staff_ids[:50]:  # First 50 are full-time
            schedule.append({
                'person_type': 'staff',
                'id': staff_id,
                'date': date_str,
                'start_time': '08:00',
                'end_time': '17:00',
                'site': site
            })

        # Part-time staff (last 10, work M/W/F only)
        if day in [0, 2, 4]:  # Mon, Wed, Fri
            for staff_id in staff_ids[50:]:
                schedule.append({
                    'person_type': 'staff',
                    'id': staff_id,
                    'date': date_str,
                    'start_time': '09:00',
                    'end_time': '14:00',
                    'site': site
                })

        # Clients (all M-F, 9-3)
        for client_id in client_ids:
            schedule.append({
                'person_type': 'client',
                'id': client_id,
                'date': date_str,
                'start_time': '09:00',
                'end_time': '15:00',
                'site': site
            })

# Write to CSV
with open('schedule.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['person_type', 'id', 'date', 'start_time', 'end_time', 'site'])
    writer.writeheader()
    writer.writerows(schedule)

print(f"Generated {len(schedule)} schedule entries")
```

Run with: `python3 generate_schedule.py`

#### 6. Microsoft Teams Setup (15 minutes)

```
1. Open Microsoft Teams
2. Navigate to the channel for emergency alerts (or create new)
   - Suggested name: "ABA Emergency Alerts"
3. Click "..." next to channel name → Connectors
4. Search for "Incoming Webhook" → Configure
5. Name: "ABA Sign-In App"
6. Upload icon (optional)
7. Click "Create"
8. COPY THE WEBHOOK URL (looks like: https://outlook.office.com/webhook/...)
9. Keep this URL handy for next step
```

**Test the webhook**:
```bash
curl -X POST "YOUR_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"text": "Test message from ABA Sign-In App - Setup Complete!"}'
```

You should see the test message appear in Teams.

---

## Day 1: Load Data and Test

### Morning (1 hour)

#### 1. Upload CSV Files

1. Visit **https://signin.youraba.com/load_data**
2. Under "Upload Staff Data":
   - Click "Choose File"
   - Select `staff.csv`
   - Click "Upload Staff CSV"
   - Wait for success message
3. Under "Upload Client Data":
   - Select `clients.csv`
   - Click "Upload Client CSV"
4. Under "Upload Schedule Data":
   - Select `schedule.csv`
   - Click "Upload Schedule CSV"
   - This may take 10-15 seconds for large files

#### 2. Configure Teams Webhook

1. Still on `/load_data` page
2. Under "Teams Webhook Configuration":
   - Paste webhook URL from Teams setup
   - Click "Save Teams Webhook URL"
3. Verify success message

#### 3. System Validation Tests

**Test 1: Sign-In Page**
- Visit **https://signin.youraba.com/**
- Verify dropdowns show all staff and clients
- Select a staff member → Click "Sign In"
- Verify success message

**Test 2: Admin Dashboard**
- Visit **https://signin.youraba.com/admin**
- Verify today's schedule shows (if scheduled for today)
- Verify recent sign-in appears in activity log

**Test 3: Emergency Roll-Call**
- Visit **https://signin.youraba.com/emergency**
- Verify "Present" section shows signed-in users
- Verify "Missing" section shows scheduled but not signed-in
- Verify contact information displays

**Test 4: Teams Integration**
- On emergency page, scroll to bottom
- Click "Send Teams Emergency Notification"
- Check Teams channel for message delivery

**Test 5: Fire Drill Report**
- Visit **https://signin.youraba.com/firedrill_report**
- Mark a few people as present/absent
- Add reasons for absences
- Click "Download Fire Drill Report"
- Verify CSV downloads correctly

### Afternoon: Staff Acceptance Testing (2 hours)

#### 4. Recruit 5 Test Users

**Invite**: 3 staff members + 2 supervisors
**Duration**: 30 minutes each

**Test Script**:
```
1. Welcome and overview (5 min)
   - Show homepage
   - Explain purpose of pilot

2. Hands-on practice (15 min)
   - Have user sign in themselves
   - Have user sign out
   - Try from different devices (tablet, phone)
   - Time how long it takes

3. Admin walkthrough (supervisors only, 10 min)
   - Show admin dashboard
   - Explain emergency page
   - Demonstrate fire drill report

4. Feedback collection (5 min)
   - What was confusing?
   - What would make it easier?
   - Any concerns?
```

#### 5. Document Issues

Create issue tracker (spreadsheet or notebook):

| # | Issue | Severity | Steps to Reproduce | Workaround | Status |
|---|-------|----------|-------------------|------------|--------|
| 1 | Name hard to find in dropdown | Low | Long list, unsorted | Use browser search (Ctrl+F) | Open |
| 2 | ... | ... | ... | ... | ... |

---

## Week 1: Pilot Launch

### Monday Launch Day

#### Morning Setup (7:30 AM - 8:30 AM)

**Physical Setup**:
- [ ] Set up 2 sign-in kiosk stations (tablets or computers)
  - One at main entrance
  - One at staff area
- [ ] Open browser to: **https://signin.youraba.com**
- [ ] Bookmark the page
- [ ] Test kiosk functionality
- [ ] Station 2 support staff at kiosks
- [ ] Post printed "How to Sign In" instructions

**Support Staff Talking Points**:
```
"Good morning! We're trying a new digital sign-in system this week.
It's easy - just find your name in the dropdown, click Sign In,
and select Fort Wayne Main. Let me show you..."
```

**Administrator Checklist**:
- [ ] Arrive early (7:30 AM)
- [ ] Verify system is online
- [ ] Test sign-in process
- [ ] Have backup paper forms ready (just in case)
- [ ] Have admin login ready
- [ ] Keep phone handy for IT support

#### Throughout the Day

**8:00 AM - 9:00 AM** (Peak arrival):
- Assist users at kiosks
- Time first-time users (target: <1 minute)
- Note any confusion or errors

**9:00 AM** (Morning checkpoint):
- Visit /admin page
- Check sign-in rate (how many have signed in?)
- Note any users who arrived but didn't sign in
- Remind stragglers

**12:00 PM** (Midday check):
- Review sign-in log
- Respond to any issues
- Quick team huddle (5 min)

**3:00 PM - 5:00 PM** (Departure time):
- Remind users to sign out
- Monitor sign-out compliance

**5:30 PM** (End of day):
- [ ] Run admin report
- [ ] Compare to manual attendance (if applicable)
- [ ] Note discrepancies
- [ ] Backup runtime/ directory
- [ ] Complete daily log
- [ ] Email summary to stakeholders

### Daily Log Template

```
ABA SIGN-IN APP - PILOT DAY LOG
Date: ___________
Administrator: ___________

METRICS:
- Total scheduled: ____
- Total signed in: ____
- Sign-in rate: ____%
- Issues reported: ____
- Support interventions: ____

ISSUES ENCOUNTERED:
1. ________________________
2. ________________________

USER FEEDBACK:
- Positive: ________________
- Negative: ________________

NOTES:
_________________________
_________________________

ACTION ITEMS FOR TOMORROW:
- [ ] ____________________
- [ ] ____________________
```

### Tuesday - Friday Week 1

**Reduce support gradually**:
- Tuesday: 2 support staff (AM only)
- Wednesday: 1 support staff (AM only)
- Thursday: 1 support staff (on-call)
- Friday: Admins only

**Wednesday**: Conduct practice fire drill
- [ ] 10:00 AM (or preferred time)
- [ ] Follow emergency drill script (see PILOT_PLAN.md Appendix D)
- [ ] Time the emergency roll-call process
- [ ] Document results
- [ ] Gather feedback

**Friday**: End-of-week review
- [ ] Compile week's metrics
- [ ] Review issue log
- [ ] Plan fixes for Week 2
- [ ] Send update to stakeholders

---

## Ongoing Monitoring (Weeks 2-4)

### Daily Tasks (15 minutes)

**Morning**:
```bash
# Check system status
systemctl status aba-signin

# Review logs for errors
tail -50 /opt/ABA-Sign-In-App/runtime/audit.log

# Verify today's schedule loaded
# (Visit /admin page)
```

**Evening**:
```bash
# Run backup
/opt/ABA-Sign-In-App/backup.sh

# Check sign-in completion rate
# (Visit /admin page, compare to schedule)
```

### Weekly Tasks (1 hour)

**Every Monday**:
- [ ] Update schedule.csv if needed (staff changes, holidays)
- [ ] Re-upload schedule via /load_data
- [ ] Review previous week's metrics
- [ ] Update issue tracker
- [ ] Send weekly update email

**Every Friday**:
- [ ] Generate weekly report (sign-ins, issues, feedback)
- [ ] Backup entire runtime/ directory to external drive
- [ ] Plan next week's activities

### Mid-Pilot Survey (Week 2)

Send to all users via email:

```
Subject: Quick Feedback on ABA Sign-In System (5 minutes)

We've been using the new sign-in system for 2 weeks. Please take 5 minutes
to share your experience:

[Link to Google Form]

Questions:
1. How easy is it to use? (1-5 scale)
2. How long does it take to sign in? (estimate)
3. What do you like about it?
4. What could be improved?
5. Any technical problems? (describe)

Thank you for helping us improve!
```

---

## Troubleshooting Quick Reference

### System Down
```bash
# Check if service is running
systemctl status aba-signin

# Restart service
sudo systemctl restart aba-signin

# Check logs
journalctl -u aba-signin -n 50
```

### Can't Find Name in Dropdown
1. Verify person is in CSV file
2. Check spelling (exact match required)
3. Re-upload CSV if needed
4. Temporary: Have user select any name, note for later correction

### Sign-In Not Recording
1. Check browser console (F12 → Console tab)
2. Verify network connection
3. Try different browser/device
4. Check if server is responding: `curl https://signin.youraba.com`

### Teams Notification Failing
1. Test webhook with curl:
   ```bash
   curl -X POST "WEBHOOK_URL" \
     -H "Content-Type: application/json" \
     -d '{"text": "Test"}'
   ```
2. Verify webhook URL is correct in /load_data
3. Check if org blocks webhooks (firewall/proxy)
4. Try re-creating webhook in Teams

### Data Looks Wrong
1. Check which CSV was uploaded (date in filename?)
2. View runtime/signins.json to see raw data
3. Restore from backup if needed:
   ```bash
   cd /opt/aba-backups
   tar -xzf runtime_YYYYMMDD_HHMMSS.tar.gz -C /
   sudo systemctl restart aba-signin
   ```

---

## Success Criteria

### Week 1 Goals
- [ ] 80% of users sign in at least once
- [ ] Zero critical system failures
- [ ] All administrators trained and confident
- [ ] Emergency drill completed successfully

### Week 4 Goals
- [ ] 95%+ daily sign-in compliance
- [ ] <5 support tickets per week
- [ ] User satisfaction >4.0/5.0
- [ ] System uptime >99%
- [ ] Data accuracy >98%

---

## Quick Links

- **Sign-In**: https://signin.youraba.com
- **Admin Dashboard**: https://signin.youraba.com/admin
- **Emergency**: https://signin.youraba.com/emergency
- **Load Data**: https://signin.youraba.com/load_data
- **Fire Drill Report**: https://signin.youraba.com/firedrill_report

---

## Support Contacts

- **Tier 1** (On-site admin): [Name], [Phone]
- **Tier 2** (IT support): [Name], [Email], [Phone]
- **Tier 3** (Developer): [Name], [Email]

---

## Next Steps

After completing this quick start:

1. Review full **PILOT_PLAN.md** for detailed procedures
2. Customize templates for your organization
3. Schedule administrator training session
4. Set pilot start date
5. Communicate timeline to all stakeholders

**Questions?** Contact: [Project Manager]

---

**Document Version**: 1.0
**Last Updated**: 2025-10-26
