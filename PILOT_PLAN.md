# ABA Sign-In App - Single Location Pilot Plan

**Target Scale**: 60 Clients + 60 Staff = 120 Users
**Duration**: 8 Weeks (2-week prep + 4-week pilot + 2-week evaluation)
**Location**: Single ABA Provider Site
**Date Prepared**: 2025-10-26

---

## Executive Summary

This document outlines a phased approach to piloting the ABA Sign-In App at a single location with approximately 120 users (60 clients and 60 staff members). The pilot will validate the system's functionality, usability, and reliability in a real-world environment while gathering feedback for future enhancements.

**Key Objectives**:
1. Validate system performance with 120 users and ~240 daily sign-in events
2. Test emergency roll-call procedures and Microsoft Teams integration
3. Gather user feedback on usability and feature gaps
4. Establish baseline metrics for attendance accuracy and system reliability
5. Identify technical and operational issues before broader deployment

---

## Phase 1: Pre-Pilot Preparation (Weeks 1-2)

### 1.1 Infrastructure Setup

#### Hosting Environment Selection
**Recommended Options**:

**Option A: Cloud VM (Recommended for Pilot)**
- Deploy on AWS EC2 t3.small or equivalent (2 vCPU, 2GB RAM)
- Ubuntu 22.04 LTS with Python 3.8+
- Nginx reverse proxy for HTTPS termination
- Cost: ~$15-20/month

**Option B: On-Premises Server**
- Dedicated workstation/server at the location
- Static IP or dynamic DNS
- Local network access with port forwarding if needed
- Cost: Hardware only

**Option C: Docker Container (Most Portable)**
- Docker container on any cloud provider or local server
- Easy migration between environments
- Included in infrastructure-as-code approach

#### Server Configuration Checklist
```bash
# Required steps:
- [ ] Install Python 3.8 or higher
- [ ] Clone repository to /opt/aba-signin-app
- [ ] Create runtime directory: /opt/aba-signin-app/runtime
- [ ] Set up systemd service for automatic startup
- [ ] Configure Nginx reverse proxy with SSL/TLS certificate
- [ ] Set up daily backup cron job for runtime/ directory
- [ ] Configure firewall (allow ports 80, 443; block 8000)
- [ ] Set environment variables for production
```

**Environment Variables for Pilot**:
```bash
export ABA_RUNTIME_DIR=/opt/aba-signin-app/runtime
export ABA_ENVIRONMENT=pilot
export ABA_TIMEZONE=America/Indiana/Indianapolis  # Adjust to location timezone
export ABA_DATA_RETENTION_DAYS=90
export ABA_WEBHOOK_TIMEOUT=15.0
export ABA_AUDIT_LOG_ENABLED=true
export ABA_LOG_LEVEL=INFO
```

#### Security Hardening
```bash
# Essential security measures:
- [ ] Enable HTTPS with Let's Encrypt certificate
- [ ] Configure Nginx basic authentication for /admin and /load_data pages
- [ ] Set restrictive file permissions (runtime/ owned by app user)
- [ ] Enable firewall (ufw or cloud security groups)
- [ ] Create non-root user to run the application
- [ ] Set up automated security updates
- [ ] Configure log rotation for audit.log
```

**Sample systemd Service** (`/etc/systemd/system/aba-signin.service`):
```ini
[Unit]
Description=ABA Sign-In Application
After=network.target

[Service]
Type=simple
User=aba-app
WorkingDirectory=/opt/aba-signin-app
Environment="ABA_RUNTIME_DIR=/opt/aba-signin-app/runtime"
Environment="ABA_ENVIRONMENT=pilot"
ExecStart=/usr/bin/python3 /opt/aba-signin-app/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Sample Nginx Configuration**:
```nginx
server {
    listen 443 ssl http2;
    server_name signin.youraba.com;

    ssl_certificate /etc/letsencrypt/live/signin.youraba.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/signin.youraba.com/privkey.pem;

    # Basic auth for admin pages
    location ~ ^/(admin|load_data|firedrill_report) {
        auth_basic "Administrator Access";
        auth_basic_user_file /etc/nginx/.htpasswd;
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
    }

    # Public sign-in page
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 1.2 Data Collection and Preparation

#### CSV Data Templates
Create spreadsheets in Google Sheets or Excel, then export as CSV:

**staff.csv Preparation**:
```csv
id,name,email,phone,site,contact_name,contact_phone
STF001,Jane Smith,jane.smith@aba.com,555-123-4567,Fort Wayne Main,Dr. Sarah Johnson,555-999-0001
STF002,John Doe,john.doe@aba.com,555-123-4568,Fort Wayne Main,Dr. Sarah Johnson,555-999-0001
...
```

**Checklist**:
- [ ] Collect staff roster from HR system (60 records)
- [ ] Assign unique IDs (suggest: STF001-STF060)
- [ ] Verify all staff email addresses and phone numbers
- [ ] Identify supervisor contact for each staff member
- [ ] Confirm site name consistency (use one canonical name)
- [ ] Validate CSV formatting (no special characters in names)

**clients.csv Preparation**:
```csv
id,name,contact_name,contact_phone,site
CLT001,Charlie Brown,Mary Brown (Mother),555-234-5678,Fort Wayne Main
CLT002,Lucy Van Pelt,Richard Van Pelt (Father),555-234-5679,Fort Wayne Main
...
```

**Checklist**:
- [ ] Collect client roster (60 records)
- [ ] Assign unique IDs (suggest: CLT001-CLT060)
- [ ] Get parent/guardian consent for emergency contact sharing
- [ ] Verify accuracy of guardian contact information
- [ ] Include relationship in contact_name (e.g., "Mary Brown (Mother)")
- [ ] Confirm HIPAA compliance for data handling

**schedule.csv Preparation**:
```csv
person_type,id,date,start_time,end_time,site
staff,STF001,2025-11-01,08:00,17:00,Fort Wayne Main
staff,STF001,2025-11-02,08:00,17:00,Fort Wayne Main
client,CLT001,2025-11-01,09:00,15:00,Fort Wayne Main
client,CLT001,2025-11-02,09:00,15:00,Fort Wayne Main
...
```

**Checklist**:
- [ ] Generate 4-week schedule (pilot duration)
- [ ] Include all 120 users' expected attendance days
- [ ] Use YYYY-MM-DD format for dates
- [ ] Use HH:MM 24-hour format for times
- [ ] Account for part-time staff/clients (variable schedules)
- [ ] Include known holidays/closures

**Data Volume Estimate**:
- Staff records: 60 rows
- Client records: 60 rows
- Schedule entries: ~2,400 rows (120 people × 20 business days)
- Expected daily sign-ins: ~240 events (120 people × 2 actions)
- Total pilot sign-in events: ~4,800 (20 days × 240 events)

#### Data Privacy and Compliance
- [ ] Obtain legal review of data collection practices
- [ ] Ensure HIPAA compliance for client data handling
- [ ] Create data processing agreement if using cloud hosting
- [ ] Document data retention and deletion procedures
- [ ] Get parent/guardian consent for client information display
- [ ] Create privacy notice for staff and clients

### 1.3 Microsoft Teams Integration Setup

**Prerequisites**:
- Microsoft Teams account with channel admin permissions
- Ability to add connectors to Teams channels

**Setup Steps**:
1. **Create Dedicated Channel**:
   - Channel name: "ABA Emergency Alerts"
   - Team: Operations or Administrative team
   - Members: All supervisors, admin staff, emergency contacts

2. **Configure Incoming Webhook**:
   ```
   - Navigate to Teams channel
   - Click "..." → Connectors → Incoming Webhook
   - Name: "ABA Sign-In App"
   - Upload icon (optional)
   - Copy webhook URL (starts with https://outlook.office.com/webhook/...)
   ```

3. **Test Webhook**:
   ```bash
   curl -X POST <webhook-url> \
     -H "Content-Type: application/json" \
     -d '{"text": "Test message from ABA Sign-In App"}'
   ```

4. **Document Webhook in App**:
   - Navigate to http://signin.youraba.com/load_data
   - Paste webhook URL in "Teams Webhook URL" field
   - Click "Save Teams Webhook URL"
   - Verify it's saved in runtime/settings.json

**Checklist**:
- [ ] Create Teams channel for emergency alerts
- [ ] Configure incoming webhook connector
- [ ] Test webhook with curl command
- [ ] Document webhook URL in app settings
- [ ] Train administrators on emergency notification procedure
- [ ] Define escalation policy for emergency alerts

### 1.4 Testing and Validation

#### Pre-Pilot Testing Schedule
**Week 1: Internal Testing**
- [ ] Load test data (10 staff, 10 clients, 5-day schedule)
- [ ] Test sign-in/sign-out workflow
- [ ] Verify admin dashboard displays correctly
- [ ] Test emergency roll-call page
- [ ] Test fire drill report generation
- [ ] Test Teams webhook notification
- [ ] Verify data persists after server restart
- [ ] Test CSV re-upload (data replacement)

**Week 2: User Acceptance Testing (UAT)**
- [ ] Recruit 5 staff members for UAT
- [ ] Conduct 30-minute training session
- [ ] Have testers perform daily sign-in/out for 3 days
- [ ] Collect usability feedback via survey
- [ ] Address any critical issues identified
- [ ] Refine training materials based on feedback

#### Performance Testing
**Load Testing** (simulate peak usage):
```python
# Simulate 120 users signing in within 30-minute window
# Expected: 4 sign-ins per minute
# Python script to test concurrent requests
```

**Benchmarks to Validate**:
- [ ] Homepage loads in < 2 seconds with 120 users in dropdowns
- [ ] Sign-in submission completes in < 1 second
- [ ] Admin dashboard renders in < 3 seconds
- [ ] Emergency page loads in < 2 seconds
- [ ] CSV upload (2,400-row schedule) completes in < 5 seconds
- [ ] Server handles 10 concurrent sign-in requests without errors

**Checklist**:
- [ ] Test with full 120-user dataset
- [ ] Verify browser compatibility (Chrome, Firefox, Safari, Edge)
- [ ] Test on mobile devices (tablets at sign-in kiosks)
- [ ] Check responsiveness of Bootstrap UI
- [ ] Verify CSV export downloads correctly
- [ ] Test edge cases (duplicate sign-ins, invalid IDs)

### 1.5 Training Material Development

#### Administrator Training Guide
**Topics to Cover**:
1. System overview and architecture
2. Data loading procedures (CSV upload)
3. Admin dashboard interpretation
4. Emergency roll-call procedures
5. Fire drill report generation
6. Teams webhook configuration
7. Troubleshooting common issues
8. Data backup and recovery
9. Privacy and compliance responsibilities

**Deliverables**:
- [ ] 10-page administrator manual (PDF)
- [ ] Quick reference guide (1-page laminated card)
- [ ] Video walkthrough (15 minutes)
- [ ] Troubleshooting FAQ document

#### Staff Training Materials
**Topics to Cover**:
1. How to sign in upon arrival
2. How to sign out when leaving
3. What to do if name not in dropdown
4. Where to find help
5. Privacy considerations

**Deliverables**:
- [ ] 2-page visual guide with screenshots
- [ ] Laminated instruction card for kiosk stations
- [ ] 5-minute training video
- [ ] One-on-one demo during first week

#### Client/Guardian Training
**Topics to Cover**:
1. Why the system is being used
2. How guardians can verify child sign-in/out
3. Privacy protections in place
4. Contact information for questions

**Deliverables**:
- [ ] Parent/guardian letter (1 page)
- [ ] FAQ handout
- [ ] Consent form for data inclusion

### 1.6 Support and Communication Plan

#### Pilot Communication Timeline

**Week -2 (2 weeks before pilot)**:
- [ ] Send announcement email to all staff
- [ ] Send parent/guardian letter to all client families
- [ ] Post informational flyer in facility
- [ ] Schedule administrator training session

**Week -1 (1 week before pilot)**:
- [ ] Conduct administrator training (2 hours)
- [ ] Distribute quick reference guides
- [ ] Set up sign-in kiosk stations (tablets/computers)
- [ ] Send reminder email to staff
- [ ] Host Q&A session for interested parents

**Week 0 (Pilot launch)**:
- [ ] Station support staff at kiosks for first 3 days
- [ ] Send "Go Live" announcement
- [ ] Monitor system closely for issues

#### Support Structure

**Tier 1 Support: On-Site Administrators**
- Contact: Site administrator (designated person)
- Hours: During operating hours (8 AM - 6 PM)
- Handles: Sign-in issues, name not found, basic troubleshooting

**Tier 2 Support: Technical Administrator**
- Contact: IT staff or technical lead
- Hours: Same-day response during business hours
- Handles: CSV uploads, system issues, Teams webhook

**Tier 3 Support: Developer/Vendor**
- Contact: Development team or consultant
- Hours: 24-hour response time
- Handles: Critical system failures, bugs, code issues

**Support Channels**:
- [ ] Dedicated email: signin-support@youraba.com
- [ ] Phone hotline: (555) 123-HELP
- [ ] Teams channel: #aba-signin-support
- [ ] Issue tracking spreadsheet for logging problems

---

## Phase 2: Pilot Execution (Weeks 3-6)

### 2.1 Week 1: Soft Launch (Training Mode)

**Objectives**:
- Get all users familiar with the system
- Run parallel with existing sign-in process (if any)
- Focus on training and support
- Low-pressure environment to learn the system

**Activities**:
- [ ] Monday 8 AM: Official pilot launch
- [ ] Station 2 support staff at kiosk areas (morning and afternoon)
- [ ] Conduct mini training sessions (5 min) for walk-up users
- [ ] Administrators run daily attendance reports
- [ ] Test emergency roll-call (planned drill on Day 3)
- [ ] Daily check-in meeting with admin team (15 min EOD)
- [ ] Log all issues in tracking spreadsheet

**Success Criteria**:
- 80% of users successfully sign in at least once
- All administrators can generate reports independently
- Zero critical system failures
- Issues logged and categorized for resolution

**Daily Checklist for Administrators**:
```
Morning (8:00 AM):
- [ ] Verify system is online
- [ ] Check for server alerts/logs
- [ ] Ensure kiosk devices are functioning
- [ ] Review yesterday's sign-in data

During Day:
- [ ] Monitor sign-in activity
- [ ] Assist users as needed
- [ ] Log any issues reported

Evening (5:30 PM):
- [ ] Run admin dashboard report
- [ ] Compare to actual attendance
- [ ] Document discrepancies
- [ ] Backup runtime/ directory
- [ ] Brief tomorrow's admin team
```

### 2.2 Week 2: Active Monitoring

**Objectives**:
- Achieve 95%+ adoption rate
- Identify usability issues and friction points
- Validate data accuracy against manual records
- Begin phasing out parallel systems (if applicable)

**Activities**:
- [ ] Reduce on-site support to 1 person (mornings only)
- [ ] Conduct first fire drill exercise (unannounced)
- [ ] Generate fire drill report and submit to admin
- [ ] Send Teams emergency notification test
- [ ] Administer mid-pilot user survey (5 questions)
- [ ] Review audit logs for unusual patterns
- [ ] Address issues from Week 1 backlog

**Metrics to Track**:
- Daily sign-in completion rate (target: 95%+)
- Average time to sign in (target: < 30 seconds)
- Number of support requests per day (target: < 5)
- System uptime (target: 99.5%+)
- Data accuracy: % match with manual attendance (target: 98%+)

### 2.3 Week 3: Optimization

**Objectives**:
- Fine-tune based on Week 1-2 learnings
- Implement quick fixes for common issues
- Stress test with full capacity
- Validate reporting accuracy

**Activities**:
- [ ] Review top 10 issues and implement fixes
- [ ] Update CSV data if schedules have changed
- [ ] Test CSV re-upload process with admin
- [ ] Conduct second fire drill (announced)
- [ ] Have admin team practice emergency procedures independently
- [ ] Reduce on-site support to on-call only
- [ ] Document process improvements

**Potential Issues to Address**:
- Names appearing in wrong order (sort by last name?)
- Dropdowns too long (add search/filter?)
- Confusion about which site to select (default selection?)
- Forgotten sign-outs (reminder system?)
- Schedule inaccuracies (easier update process?)

### 2.4 Week 4: Validation and Documentation

**Objectives**:
- Validate system operates independently
- Document all processes and procedures
- Prepare for evaluation phase
- Collect final user feedback

**Activities**:
- [ ] Remove all on-site support (admins only)
- [ ] Conduct final fire drill with full documentation
- [ ] Administer end-of-pilot user survey (10 questions)
- [ ] Conduct focus group with 8-10 staff members (1 hour)
- [ ] Interview administrators about experience
- [ ] Generate 4-week usage report (total sign-ins, patterns)
- [ ] Document all workarounds and manual processes still needed
- [ ] Compile issue log with severity ratings

**Data to Collect**:
- Total sign-in events: ______
- Total unique users who signed in: ______
- Average daily sign-in rate: ______%
- Number of incidents/issues: ______
- Average resolution time: ______
- User satisfaction score (1-5): ______
- System uptime: ______%

---

## Phase 3: Evaluation and Decision (Weeks 7-8)

### 3.1 Data Analysis

#### Quantitative Metrics

**System Performance**:
| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| User adoption rate | >95% | ___% | Pass/Fail |
| Daily sign-in accuracy | >98% | ___% | Pass/Fail |
| System uptime | >99% | ___% | Pass/Fail |
| Average sign-in time | <30s | ___s | Pass/Fail |
| Support tickets/week | <20 | ___ | Pass/Fail |
| Critical failures | 0 | ___ | Pass/Fail |

**Usage Patterns**:
- Peak sign-in times (identify kiosk bottlenecks)
- Most common user errors
- Features most/least used
- Schedule accuracy (planned vs. actual)

**Data Integrity**:
- Audit log completeness (100% of actions logged?)
- Snapshot recovery success (test restore from backup)
- CSV upload error rate
- Teams webhook delivery success rate

#### Qualitative Feedback

**User Survey Questions** (1-5 Likert scale):
1. The system was easy to learn and use
2. I could always find my name in the dropdown
3. The sign-in process was faster than our old method
4. I encountered technical problems (reverse scored)
5. I would recommend continuing to use this system

**Administrator Interview Questions**:
1. What were the biggest challenges during the pilot?
2. How accurate were the attendance reports?
3. Was the emergency roll-call feature useful?
4. What features are missing or need improvement?
5. How much time did the system save/cost compared to manual tracking?
6. What concerns do you have about long-term use?

**Staff Focus Group Topics**:
- First impressions and learning curve
- Comparison to previous sign-in methods
- Suggestions for improvement
- Privacy and security concerns
- Impact on daily workflow

### 3.2 Issue Resolution and Prioritization

**Issue Categorization**:

**Critical (Must fix before full deployment)**:
- System crashes or data loss
- Security vulnerabilities
- HIPAA compliance gaps
- Emergency feature failures

**High (Should fix soon)**:
- Usability issues affecting >20% of users
- Performance problems during peak times
- Reporting inaccuracies
- Training material gaps

**Medium (Plan for future release)**:
- Feature requests from multiple users
- Minor UI improvements
- Process optimizations
- Documentation updates

**Low (Nice to have)**:
- Individual user preferences
- Edge case handling
- Cosmetic changes

### 3.3 Go/No-Go Decision Framework

#### Criteria for Full Deployment

**Must Have (All required)**:
- [ ] >90% user adoption rate
- [ ] >95% data accuracy
- [ ] Zero critical security issues
- [ ] Successful emergency drill demonstrations
- [ ] Administrator confidence in system operation
- [ ] Legal/compliance approval
- [ ] Stable system (no crashes in final 2 weeks)

**Should Have (75% required)**:
- [ ] >85% user satisfaction score
- [ ] <10 support tickets per week
- [ ] All admin training completed
- [ ] Parent/guardian acceptance
- [ ] Clear ROI (time/cost savings)
- [ ] Documented processes for all operations
- [ ] Backup and recovery plan tested

**Nice to Have**:
- [ ] Feature requests prioritized and roadmapped
- [ ] Integration with other systems explored
- [ ] Long-term hosting plan finalized
- [ ] Budget approved for enhancements

#### Possible Outcomes

**Green Light: Proceed with Full Deployment**
- Expand to additional locations
- Plan feature enhancements based on feedback
- Establish ongoing support model
- Document lessons learned for future sites

**Yellow Light: Extend Pilot**
- Continue pilot for additional 4 weeks
- Address critical issues identified
- Re-evaluate with updated criteria
- Expand pilot to second location for comparison

**Red Light: Pause or Redesign**
- Critical issues cannot be resolved quickly
- User adoption too low (<70%)
- Data accuracy concerns
- Better alternatives identified
- Revert to previous system while redesigning

### 3.4 Final Deliverables

**Pilot Report** (15-20 pages):
1. Executive summary
2. Pilot objectives and methodology
3. Quantitative results (metrics, charts)
4. Qualitative feedback summary
5. Issue log and resolutions
6. Lessons learned
7. Recommendations
8. Next steps and timeline

**Supporting Documents**:
- [ ] User survey results (raw data + analysis)
- [ ] Administrator interview transcripts
- [ ] Focus group notes
- [ ] System logs and analytics
- [ ] Updated training materials
- [ ] Process documentation
- [ ] Issue tracking spreadsheet
- [ ] Cost analysis (time/resources spent)

**Presentation for Stakeholders** (30 slides):
- Pilot overview and objectives
- Key metrics and results
- User feedback highlights
- Demonstrations (screenshots, live demo)
- Issues encountered and solutions
- Cost-benefit analysis
- Recommendation and rationale
- Proposed rollout plan (if approved)

---

## Risk Management

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Server failure during pilot | Low | High | Daily backups, documented recovery procedure, backup laptop ready |
| Data loss | Low | Critical | Automated backups every 6 hours, test restore weekly |
| Network outage | Medium | Medium | Have paper backup forms, enter data retroactively |
| Performance degradation | Low | Medium | Load test beforehand, monitor daily, scale if needed |
| Browser compatibility issues | Medium | Low | Test on all devices/browsers before launch |
| CSV data corruption | Medium | Medium | Validate CSVs before upload, keep original files |

### Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Low user adoption | Medium | High | Extensive training, on-site support first week, incentives |
| Resistance to change | Medium | Medium | Stakeholder buy-in, explain benefits, address concerns |
| Inadequate training | Low | High | Multiple training formats, ongoing support, reference materials |
| Privacy concerns | Medium | High | Legal review, consent forms, HIPAA compliance audit |
| Support capacity overwhelmed | Low | Medium | Tiered support structure, escalation procedures |
| Administrator turnover | Low | Medium | Cross-train multiple admins, document everything |

### Compliance and Legal Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| HIPAA violation | Low | Critical | Legal review, encrypt data, access controls, audit logging |
| Parental consent gaps | Medium | High | Explicit consent forms, opt-out option, clear communication |
| Data breach | Low | Critical | Security hardening, HTTPS, restricted access, monitoring |
| Liability for inaccurate data | Low | High | Disclaimers, data validation, parallel systems during pilot |

---

## Success Metrics and KPIs

### Primary Success Metrics

1. **User Adoption Rate**
   - Formula: (Unique users who signed in / Total users) × 100
   - Target: >95%
   - Measurement: Weekly average over 4-week pilot

2. **Data Accuracy**
   - Formula: (Correct sign-ins / Total sign-ins) × 100
   - Target: >98%
   - Measurement: Compare to manual attendance records daily

3. **System Reliability**
   - Formula: (Uptime minutes / Total minutes) × 100
   - Target: >99%
   - Measurement: Automated uptime monitoring

4. **User Satisfaction**
   - Formula: Average survey score (1-5 scale)
   - Target: >4.0
   - Measurement: End-of-pilot survey

### Secondary Success Metrics

5. **Time Savings**
   - Measure: Time to complete sign-in vs. previous method
   - Target: >50% reduction
   - Measurement: Observe 20 users, time with stopwatch

6. **Administrative Efficiency**
   - Measure: Time to generate attendance reports
   - Target: <5 minutes (vs. 30+ min manual)
   - Measurement: Administrator time logs

7. **Emergency Preparedness**
   - Measure: Time to generate emergency roll-call
   - Target: <2 minutes
   - Measurement: Fire drill exercises

8. **Support Load**
   - Measure: Support tickets per week
   - Target: <10 after Week 2
   - Measurement: Issue tracking system

### Leading Indicators (Monitor Weekly)

- Daily sign-in completion rate (early warning for adoption issues)
- Number of users signing in for first time (onboarding progress)
- Average sign-in time (usability indicator)
- Number of schedule updates needed (data quality)
- Support ticket volume and types (problem areas)

---

## Budget and Resource Allocation

### Infrastructure Costs (4-Week Pilot)

| Item | Cost | Notes |
|------|------|-------|
| Cloud VM (AWS t3.small) | $20 | Monthly, prorated |
| Domain name | $12/year | signin.youraba.com |
| SSL certificate | $0 | Let's Encrypt (free) |
| Backup storage | $5 | 50GB cloud storage |
| Microsoft Teams | $0 | Using existing license |
| **Total Infrastructure** | **~$40** | One-time + monthly |

### Hardware (One-Time)

| Item | Cost | Notes |
|------|------|-------|
| Tablet/kiosk devices (2) | $400 | iPad or Android tablets for sign-in stations |
| Stands/enclosures | $100 | Secure mounting for tablets |
| Backup laptop | $0 | Repurpose existing device |
| **Total Hardware** | **$500** | Reusable for full deployment |

### Personnel Time (Internal Costs)

| Role | Hours | Rate | Cost |
|------|-------|------|------|
| Technical setup (IT) | 16 hrs | $50/hr | $800 |
| Administrator training | 8 hrs | $30/hr | $240 |
| Data preparation (HR) | 12 hrs | $25/hr | $300 |
| On-site support (Week 1) | 40 hrs | $20/hr | $800 |
| Project management | 20 hrs | $40/hr | $800 |
| Evaluation and reporting | 16 hrs | $40/hr | $640 |
| **Total Personnel** | **112 hrs** | | **$3,580** |

### Training and Materials

| Item | Cost | Notes |
|------|------|-------|
| Printed materials | $50 | Guides, reference cards |
| Video production | $0 | Internal screen recording |
| Surveys and forms | $0 | Google Forms |
| **Total Training** | **$50** | |

### Contingency

| Item | Cost | Notes |
|------|------|-------|
| Unexpected issues | $500 | 10% contingency fund |

### **Total Pilot Budget: ~$4,670**

**ROI Calculation**:
If system saves 2 hours/week of administrative time at $30/hr:
- Annual savings: $3,120/year (52 weeks × 2 hrs × $30)
- Payback period: ~18 months
- Does not include improved accuracy, emergency preparedness value

---

## Post-Pilot Rollout Plan (If Approved)

### Immediate Next Steps (Weeks 9-10)

1. **Address Critical Issues**
   - Fix any bugs or usability problems identified
   - Update documentation based on lessons learned
   - Refine training materials

2. **Prepare for Scale**
   - Evaluate hosting for multi-location deployment
   - Plan database migration (if needed for scale)
   - Design multi-site architecture

3. **Stakeholder Approval**
   - Present pilot results to leadership
   - Get budget approval for full deployment
   - Obtain legal/compliance sign-off

### Phase 1 Rollout: Additional Locations (Months 3-4)

- Deploy to 2-3 additional locations simultaneously
- Stagger by 2 weeks to manage support load
- Use lessons learned from pilot site
- Refine support model based on demand

### Phase 2 Rollout: Organization-Wide (Months 5-6)

- Deploy to all remaining locations
- Establish central support team
- Implement monitoring and alerting
- Plan feature enhancements based on feedback

### Long-Term Enhancements (Months 7-12)

Based on ENTERPRISE_PLAN.md priorities:
1. Database migration (PostgreSQL)
2. Authentication system (OAuth 2.0)
3. Mobile app for staff/parents
4. SMS/email notifications
5. Integration with scheduling software
6. Advanced reporting and analytics

---

## Appendices

### Appendix A: Daily Operations Checklist

**Morning Routine (8:00 AM)**:
```
- [ ] Check system status (visit homepage)
- [ ] Review overnight logs in runtime/audit.log
- [ ] Verify kiosk tablets are powered on and connected
- [ ] Ensure today's schedule is loaded
- [ ] Test sign-in with admin account
```

**Evening Routine (5:30 PM)**:
```
- [ ] Run admin dashboard report
- [ ] Export fire drill report (if drill occurred)
- [ ] Compare sign-ins to schedule (note discrepancies)
- [ ] Backup runtime/ directory to USB or cloud
- [ ] Complete daily log entry
- [ ] Brief next-day administrator
```

### Appendix B: Troubleshooting Guide

**Issue: User's name not in dropdown**
- Check if user is in correct CSV (staff vs. client)
- Verify CSV was uploaded successfully
- Check for typos in name or ID
- Have user sign in as "Other" temporarily
- Update CSV and re-upload

**Issue: System not responding**
- Check if server is running: `systemctl status aba-signin`
- Check server logs: `tail -f runtime/audit.log`
- Restart service: `systemctl restart aba-signin`
- Verify network connectivity
- Contact Tier 2 support if issue persists

**Issue: Teams notification not sending**
- Verify webhook URL is correct in settings
- Test webhook with curl command
- Check if organization blocks outbound webhooks
- Review error message on emergency page
- Try reconfiguring webhook in Teams

**Issue: Sign-in button not working**
- Check browser console for JavaScript errors
- Try different browser
- Clear browser cache
- Verify network connection
- Have user try from different device

### Appendix C: Data Privacy Statement (Sample)

```
ABA SIGN-IN APP - PRIVACY NOTICE

Purpose: This system tracks attendance for safety, accountability, and
operational purposes.

Data Collected:
- Staff: Name, ID, email, phone, supervisor contact
- Clients: Name, ID, guardian/parent contact
- Sign-in/out times, dates, and locations

Data Usage:
- Attendance tracking and reporting
- Emergency roll-call and accountability
- Operational planning and compliance

Data Protection:
- Encrypted in transit (HTTPS)
- Access restricted to administrators
- Audit logging of all actions
- Daily backups with 90-day retention
- HIPAA-compliant handling procedures

Your Rights:
- Review your data upon request
- Request corrections to inaccurate data
- Opt out of non-essential data collection (contact admin)

Questions: Contact [privacy@youraba.com] or (555) 123-4567
```

### Appendix D: Emergency Drill Script

**Fire Drill Procedure Using ABA Sign-In App**:

1. **Trigger alarm** (9:00 AM or predetermined time)

2. **Evacuate all staff and clients** to designated assembly area

3. **Administrator actions** (within 2 minutes):
   - Navigate to http://signin.youraba.com/emergency
   - Review "Present" list (those who signed in today)
   - Review "Missing" list (scheduled but not signed in)

4. **Physical headcount** at assembly area:
   - Take attendance visually
   - Cross-reference against "Present" list
   - Identify anyone present who didn't sign in
   - Identify anyone absent who did sign in

5. **Contact missing individuals**:
   - Use contact info from "Missing" section
   - Call supervisors (staff) or guardians (clients)
   - Document each contact attempt

6. **Document drill**:
   - Navigate to /firedrill_report
   - Mark each person as present/absent
   - Add accountability reasons for absences
   - Download CSV report
   - File report with safety records

7. **Send Teams notification** (optional):
   - Click "Send Teams Emergency Notification"
   - Verify delivery in Teams channel

8. **Debrief**:
   - Compare system data to actual headcount
   - Note discrepancies (late sign-ins, early departures)
   - Identify system improvements needed

**Target Times**:
- Emergency page access: <30 seconds
- Initial accountability report: <2 minutes
- All contacts reached: <15 minutes
- Final documentation: <30 minutes

---

## Conclusion

This pilot plan provides a structured, phased approach to validating the ABA Sign-In App in a real-world environment with 120 users. By following this plan, the organization will:

1. **Minimize risk** through careful preparation and testing
2. **Gather data** to make informed go/no-go decisions
3. **Build confidence** among users and stakeholders
4. **Identify issues** early before broader deployment
5. **Establish processes** for long-term operational success

**Critical Success Factors**:
- Executive sponsorship and support
- Adequate training and support during launch
- Open communication and feedback channels
- Flexibility to adapt based on learnings
- Clear decision criteria for next steps

**Next Action**: Review this plan with stakeholders, adjust timelines and budget as needed, and proceed with Phase 1 preparation activities.

---

**Document Version**: 1.0
**Last Updated**: 2025-10-26
**Owner**: [Project Manager Name]
**Approvers**: [Leadership Names]
