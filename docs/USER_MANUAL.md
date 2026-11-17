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

## Equipment & shift custody

The shared **Equipment & custody** page works with database-backed assets and issue transactions; it is available to all signed-in roles while backend permissions govern each operation.

- Head/System Administrator: register each device/accessory separately under a unique asset number, add a private PNG/JPEG photo, print its QR label, link accessories, correct asset details, assign dated shift custodians/replacements, and record post-return inspection. Never merge several physical units into a quantity-only record or invent a serial number.
- Head of Office: configure permitted authorization roles before any borrowing. A blank policy blocks approvals. Keep this role distinct from the person physically handing an item over.
- Requester: select device(s), request shift/date, borrower/office, purpose and due time. Linked accessories are automatically added as separate item lines. External office requests are limited to Head/Editor users.
- Configured authorizer: record the authorization method and remarks. The actual scheduled custodian/replacement then records each pre-issue condition and issues the items; non-custodians and unauthorized requests are rejected server-side.
- Internal borrower: sign in as the named borrower and acknowledge receipt. For external borrowing, the shift custodian records the borrower's matching name/acknowledgement.
- At shift change, outgoing and incoming custodians each acknowledge a handover snapshot of outstanding issue items. Record discrepancies. This never marks any borrowed device returned.
- Receiving custodian: choose their receiving shift/date, list the items physically returned with condition/damage, and separately report missing items. Partial returns are supported; unreturned/missing items remain open. Damaged items remain unavailable until inspected and given an explicit disposition.
- Head/System Administrator reports show assignments/replacements, issues/returns by custodian, current/external/overdue borrowing, missing/damaged assets and handover history. Head/System Administrator can open each asset's full event and record-change history.

Do not perform database edits to “fix” a loan. Use the application workflow so actor identity, timestamps and audit history are retained. See [Equipment & shift custody](EQUIPMENT_MANAGEMENT.md) for the end-to-end acceptance procedure.

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
