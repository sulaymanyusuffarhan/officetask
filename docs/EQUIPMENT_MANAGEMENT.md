# Equipment & shift custody module

## Setup prerequisites

The module uses the same PostgreSQL database, authenticated sessions, CSRF protection and audit log as the Office Task system. Apply the migration through the normal Windows installer/update flow. The CLI seeds Morning, Afternoon and Evening shifts on a new installation; the System Administrator can adjust times in Accounts & setup. Existing installations retain existing shift times and can add any missing standard shifts using `init-db`.

1. Create the Head of Office, working staff, editors and shift leaders first. Do not use the technical administrator as a day-to-day borrower approver unless the Head explicitly delegates that role in the equipment policy.
2. The Head opens **Equipment & custody → Authorization roles** and saves permitted authorizer roles. This policy starts empty on migration, so issue authorization is denied until the Head configures it. Head-of-Office and Editor authorization methods require the corresponding acting role; any configured delegated role uses “Other delegated authorization.”
3. The Head or System Administrator assigns one or more custodians per shift and effective dates. For an absence, record a replacement, the original custodian, replacement custodian and reason. Assignments and replacements are retained as history; there is no delete endpoint.
4. Register each physical device and individually identifiable accessory as its own asset with a unique asset number (for example CAM-001 and LENS-001). Serial number is optional. Upload a PNG/JPEG photograph and open the QR label to print or scan the generated asset-number code. Never invent a manufacturer serial number. Assets without a photograph are incomplete and cannot be requested for issue.
5. Link a main device to accessories. When a main asset is requested, its directly linked accessories are included in the request as separate asset line items. Further generations of nested accessories are intentionally disallowed; link all items directly to the kit's main asset.

## Issue / return workflow

1. A borrower or authorized office user creates a request, selects a shift/date, borrower/office, purpose and expected return time. External office borrowing is restricted to Head/Editor requesters and requires an external borrower name and office.
2. A user whose role is included in the Head-configured policy approves the pending request. The record captures that person's ID, role, timestamp, selected authorization method and remarks. A custodian cannot skip this step.
3. The actual person physically issuing the items must be in the assigned or replacement roster for the request shift/date. They inspect and record the pre-issue condition of each asset. This is independent of who assigned the shift or created the request.
4. The internal borrower signs in and acknowledges receipt; for an external office, the scheduled custodian records the borrower's matching name and acknowledgement. Issue events capture the issuer and exact timestamp per physical asset.
5. At shift change, the outgoing and incoming custodians create a handover (which can be between different shifts), review the automatically snapshotted outstanding loans, each acknowledge, record discrepancies, and the Head can review. A handover does not return or close any loan.
6. On return, the actual receiving custodian chooses their receiving shift/date and records each physically returned item, its condition, damage note and any items reported missing. Partial returns are supported. Items not physically received remain outstanding; reported missing assets stay unavailable. Damaged assets remain unavailable until Head/System Administrator records an inspection disposition.
7. Head/System Administrator uses the equipment dashboard/reports and per-asset history to trace authorization, borrower, issuing custodian, receiving custodian, handover acknowledgements, missing/damaged events and record edits.

## Authorization and responsibilities

- Head of Office: configures which roles can authorize, reviews handovers and manages equipment policy.
- System Administrator: manages asset records and custodian rosters, photos and inspection disposition; not automatically an authorizer.
- Configured authorizer: records method, identity/role, time and remarks.
- Assigned custodian or recorded replacement: records physical issue/receipt. API validation checks the correct shift/date roster.
- Borrower: acknowledges internal receipt. External acknowledgement is recorded by the assigned custodian with the borrower's name.

The application never deletes completed issue/return events. Corrections to asset metadata are recorded in audit logs. Physical issue, authorization, borrower acknowledgement, return/damage/missing, custodian replacement and handover actions are stored as immutable event/audit history. Duty dates and shift windows use `OFFICE_TIMEZONE` (default `Africa/Dar_es_Salaam`); transaction timestamps are persisted as UTC and returned with a `Z` timezone marker. Set the correct IANA zone in `.env` for the actual office. Restrict direct database access; the application audit log is not tamper-proof against database administrators.

## Reports and acceptance scenario

Equipment & custody provides live indicators for shift custodians, items in custody, current-shift issues/returns, open/overdue/missing/damaged equipment, pending authorization and inspection. Head/System Administrator reports include custodian accountability and replacement history, issues/returns by custodian, current borrowing, external borrowing, overdue borrowers, missing/damaged assets, handovers, and individual asset history.

Automated API test `tests/test_equipment.py::test_shift_custodian_issue_handover_partial_return_and_traceability` runs the requested scenario using real database rows in isolated SQLite: the editor requests camera + linked lens/battery/charger; Head authorizes; morning custodian issues; borrower acknowledges; morning-to-evening custodians hand over and both acknowledge without returning items; evening custodian receives camera/lens/battery and reports charger missing; charger remains outstanding; Head can trace issuer, authorizer, borrower and receiver.

This automated test does not replace the office acceptance run. Before live use, repeat the scenario using the actual PostgreSQL deployment, assigned employees, supported browser, and real shift/hardware process. Record evidence for photo/QR scanning, reports, access roles, concurrent requests and backup/restore. Windows 11, Docker/PostgreSQL runtime, browser-wide UI and networked physical devices have not been run in the development environment.
