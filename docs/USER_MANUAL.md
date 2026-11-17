# Office user manual

## Sign-in and navigation

Open the internal office URL and sign in with the individual username/password supplied by the administrator. Do not share accounts. Your role controls available operations. Use **Change password** after first sign-in if a temporary password was used; passwords must be at least 12 characters. Use **Sign out** on shared computers. Sessions expire after the configured idle/lifetime window.

The interface has Overview, Tasks, Weekly timetable, Shift reports and (for the Head) Performance. System setup and audit history are role-restricted. The system administrator is a technical role and cannot approve schedules or verify work merely by being an administrator.

## Staff / employee

1. **Tasks** shows your assignments, due dates, priority and instructions.
2. Select **Acknowledge** when you accept an assignment, and **Start work** when work begins.
3. **Submit work** requests a written completion report and optional supporting notes/file(s). Allowed extensions are PDF, PNG/JPG, DOCX and XLSX; each file is limited by `MAX_UPLOAD_SIZE_MB` (default 20 MB), with a maximum of 10 attachments per submission.
4. View submissions to see editor feedback and authorized attachments. After correction requested/rejected, resubmit the updated work.
5. Your timetable shows only published assignments involving you. Draft schedules are not authoritative.

## Weekly timetable planner

1. Start with a Monday date and create a draft. Add allocations with date, shift, staff member, leader/editor, department and the timetable responsibility (for example Reporting, Mpira NBC or Jioni).
2. The server rejects dates outside the selected week and conflicting overlapping allocations for the same person.
3. Edit/remove draft allocations. Edits record previous/new values and a reason; a planner can edit their own draft/returned plan, not one already submitted.
4. Copy an existing week to another Monday; review all copied dates/staff/shift times.
5. Submit the non-empty plan to the Head. Read any return comment and correct/resubmit.

## Head of Office

- Review submitted plans using Begin review, Return, or Approve. Publish only an approved plan. A published schedule is locked; create a new version and provide a reason before making changes.
- Use the management dashboard for live counts and weekly staff activity. Assignments and planned staff are drawn from published timetable data.
- Create/assign tasks to one or more active staff accounts; each person receives a separate reference and independent task record. Use priority and due date carefully.
- Review work as appropriate, record attendance/leave/reassignment, reopen verified tasks only with an audit reason, and use Performance filters plus PDF/Excel/CSV exports.
- Review shift reports and audit history regularly.

## Editor

- Assign day-to-day tasks to the authorized staff list and provide instructions/deadlines.
- View your assignment queue, open a submission and choose Verify, Request correction or Reject. Add clear actionable feedback. Never verify your own work; the server enforces the independent-review restriction.
- Record the shift handover, unfinished responsibilities, challenges and attendance notes at shift end.

## Shift leader

- Review today's assigned team tasks and overdue work, then submit a shift handover report with unfinished items, challenges, attendance notes and handover.

## System administrator

- Use Accounts & setup to create/deactivate accounts, reset passwords, and add departments/shifts. Protect initial passwords and the `.env` file.
- Technical administration does not authorize schedule approval or task verification. Use the assigned Head/Editor account for business decisions.
- Audit history is view-only. Do not try to edit records directly in PostgreSQL.

## Status definitions

- **Assigned**: allocated to the employee.
- **Acknowledged / In Progress**: employee confirmation/work underway.
- **Submitted / Resubmitted**: work sent to review; not yet verified.
- **Correction Requested / Rejected**: reviewer feedback requires action; employee may resubmit.
- **Verified**: an authorized independent reviewer approved the submission.
- **Overdue**: derived when deadline passes for unfinished work; approved leave/absence/reassignment is represented separately in attendance exceptions.
- **Cancelled**: reserved terminal status for an authorized future cancellation workflow.

A submitted report is not equivalent to a verified result. A missing submission alone is not proof of poor performance; review attendance, approved leave, reassignment and operational reasons.
