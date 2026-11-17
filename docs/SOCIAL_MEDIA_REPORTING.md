# TBC Digital social media performance reporting

## Operating model: manual first, API optional later

The module is usable without social-media API credentials, developer accounts, or API access. It does not scrape websites, contact platform APIs, or request/store social account passwords or access tokens. Manual entry is the default record source; spreadsheet imports are marked separately. The schema leaves a source value for future authorized API ingestion, but this release implements no API connection and no API credentials are needed.

No official profile handles or historical analytics figures were supplied with the request. Therefore, the application does not invent profile identifiers or prefill statistics. The Head of Office registers the real verified profile name, handle/channel identifier, and optional public URL for each of the five platform records before reporting starts. The UI lists YouTube, Facebook, Instagram, X and TikTok even before their real profile details are configured.

## Roles and initial setup

1. Sign in as Head of Office and open **TBC Digital social media**.
2. In **Official platform accounts**, register all five real profiles. Check spelling and public profile links against the official institutional account. Only the profile's public identifier is stored—never a platform password/token.
3. In **Designate social media reporting officers**, select the authorized staff account(s). The module allows the Head and designated officers to access data; only the Head can configure accounts/officers and review/approve. Other roles receive backend 403 responses. A report author cannot approve their own weekly or quarterly report.
4. Start with a real platform analytics screenshot/report for the reporting period; use test fixtures only in isolated automated tests. Do not copy test numbers into production.

The app cannot determine from this repository alone which real-world profiles belong to TBC Digital; verification is an office setup responsibility.

## Weekly manual entry and evidence

Each platform has a separate weekly form. Enter the reporting date and the Monday starting the reporting week (the reporting week is Monday–Sunday). Every metric field is explicit: enter a whole number, including `0` only when the source actually reports zero, or leave the displayed `N/A` marker for unavailable/not-applicable data. The API requires each metric key; missing values are not defaulted to zero. The number of followers/subscribers at the beginning and end, new and lost followers, reach, impressions, views, likes, comments, shares, saves, posts, and videos are stored as nullable whole numbers.

A weekly report also records the best-performing content and comments/recommendations. Attach supporting evidence (up to ten files total per report, 20 MB each): PNG/JPEG analytics screenshots or PDF, XLSX, and CSV reports. Evidence is stored in the private upload folder under a random storage name, downloaded only through an authenticated route, and its original filename, type, size, uploader and time are recorded. At least one evidence file is required before submitting a weekly report.

On save the report is a **Draft**, attributed to the authenticated enterer and timestamped. Submit it to the Head for approval. The Head may **Approve**, **Reject** with a reason, or **Request correction** with a reason. A correction/rejection can be edited and resubmitted; changes are auditable. Submitted and approved records cannot be silently edited. Approved records are immutable. Duplicate account/platform + reporting-week records are rejected at both the API and database constraint level.

## Calculations and N/A policy

Calculations are derived from saved input only:

- **Weekly net audience growth:** ending audience minus beginning audience when both are present. If either endpoint is unavailable, the module falls back to new followers minus lost followers only when both flow values are present. Otherwise it is N/A.
- **Audience growth percent:** net audience growth divided by beginning audience × 100; it is N/A when the starting audience is N/A or zero.
- **Monthly/quarterly audience growth:** within the selected/grouped period, last ending audience minus first beginning audience. If an audience endpoint is unavailable, the module falls back to total new followers minus total lost followers only when every included weekly flow value is available. The percentage is net growth divided by the first beginning audience; it remains N/A if that baseline is unavailable or zero. Activity totals are available only when every included weekly report has that metric; if any is N/A, the period total stays N/A rather than treating missing values as zero.
- **Engagement rate:** YouTube/TikTok = (likes + comments + shares + saves when supplied) ÷ views × 100. Facebook/Instagram/X use reach as the denominator. Likes, comments and shares must all be available; if a required input or denominator is N/A/zero, the rate is N/A. Saves are added only if supplied, since that metric may not be available. The formula and denominator appear in analytics/report data.
- **Publishing output:** posts and videos are reported as period totals only when their weekly source values are all available.

The graphics filter to **approved weekly reports**. Select dates, a platform (or all platforms), and weekly/monthly/quarterly grouping. The views include audience growth, five-platform comparison, engagement, reach, impressions, views, posts and videos. The comparison table shows changes from the preceding reported interval for each platform when available; it is current minus previous, and an unavailable side remains N/A. Graphs and comparisons are generated from saved approved rows; no mock dataset is seeded. N/A is explicitly labeled and omitted from bars.

## Excel/CSV import

1. Download the blank CSV or Excel import template. The workbook contains a separate instructions sheet and no sample statistics.
2. Enter one row per platform/week. Use the exact platform IDs `youtube`, `facebook`, `instagram`, `x`, or `tiktok`; use ISO dates (`YYYY-MM-DD`), a Monday `reporting_week`, all metric columns, and `N/A` for unavailable figures. The columns are `platform`, `reporting_date`, `reporting_week`, the 13 metric keys shown in the template, `best_content`, and `recommendations`.
3. Upload through **Import from Excel or CSV**. Preview shows row errors and existing/within-file duplicate periods. No rows are saved when preview has errors. Correct the file and preview again.
4. Confirm import after a clean preview. Server-side validation is repeated before insertion. Imports are marked **Imported from file**, and the original file is retained as private evidence for every created draft. Duplicate periods are blocked, including concurrent inserts by the database unique constraint.
5. Imported drafts still need officer review, evidence-aware submission and Head approval; import does not approve data.

## Quarterly consolidation and management approval

A quarterly report consolidates **approved weekly reports** that overlap the selected calendar quarter. It captures a snapshot with the weekly source report IDs, platform coverage, baseline/end audience, net and percentage growth, available metric totals, and N/A values. Partial reporting coverage is shown as `weeks_reported`; no missing platform/week is padded with fabricated values. The methodology and calendar-quarter overlap rule are included in the snapshot.

The reporting officer generates the quarter, adds management analysis/recommendations, then submits it. The Head can approve, reject, or request correction. Correction allows the notes to be revised, and the data snapshot may be regenerated only before submission; submitted/approved history is locked. Weekly approved records are themselves immutable. PDF and Excel downloads include the saved snapshot, status, platform coverage, metrics, N/A, method and management notes.

## Exports and auditability

Weekly filtered PDF/XLSX exports contain the actual saved report data, calculated metrics/formula, status/source and entry attribution. Quarterly PDF/XLSX exports are generated from the immutable saved quarterly snapshot. Excel text cells are protected against formula injection. Social account configuration, officer designation, report creation/correction, import, evidence upload, submission, and decisions are application-audited. The report shows whether its source was **Manually entered**, **Imported from file**, or **Retrieved through authorized API**; only the first two are currently operational.

## Testing and acceptance boundary

Run `pytest -q` plus `node --test tests/test_social_charts.cjs` for local automated tests. The API tests use isolated SQLite and synthetic test-only fixtures; these are not official TBC statistics and are not written into a deployment database. They exercise all five account registrations, representative role denials, manual N/A entry, formula calculations, evidence handling, weekly approval/correction, imports and duplicate validation, quarterly consolidation/approval/immutability, chart data and PDF/XLSX output. The SVG renderer itself has Node unit tests.

Those checks do not replace entering the five actual verified profile identifiers, checking screenshots against live platform analytics, browser review, live PostgreSQL migration/backup tests, or Windows 11 office acceptance. No real statistics or official handles were provided, so those items must be completed by the office's designated officer and IT/management reviewers before the module is accepted for production use.
