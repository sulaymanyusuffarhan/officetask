(() => {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const state = { user: null, csrf: "", people: [], shifts: [], departments: [], activeView: "dashboard" };
  const loginPanel = $("#login-panel"), workspace = $("#workspace"), flash = $("#flash");
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const today = () => new Date().toISOString().slice(0, 10);
  const monday = () => { const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return d.toISOString().slice(0, 10); };
  const localDateTime = value => { const d=new Date(value); d.setMinutes(d.getMinutes()-d.getTimezoneOffset()); return d.toISOString().slice(0,16); };
  const isRole = (...roles) => state.user && roles.includes(state.user.role_id);
  function message(text, kind = "") { flash.textContent = text; flash.className = `message ${kind}`; flash.hidden = false; window.setTimeout(() => flash.hidden = true, 6500); }
  async function api(url, options = {}) {
    const opts = { credentials: "same-origin", ...options };
    opts.headers = new Headers(opts.headers || {});
    if (opts.body instanceof URLSearchParams) { opts.headers.set("Content-Type", "application/x-www-form-urlencoded;charset=UTF-8"); opts.body = opts.body.toString(); }
    else if (opts.body && !(opts.body instanceof FormData) && typeof opts.body !== "string") { opts.headers.set("Content-Type", "application/json"); opts.body = JSON.stringify(opts.body); }
    if (!(["GET", "HEAD"].includes((opts.method || "GET").toUpperCase())) && state.csrf) opts.headers.set("X-CSRF-Token", state.csrf);
    const res = await fetch(url, opts);
    if (res.status === 401 && !url.endsWith("/auth/login")) { showLogin(); throw new Error("Your sign-in session expired. Please sign in again."); }
    const type = res.headers.get("content-type") || "";
    const data = type.includes("application/json") ? await res.json() : await res.text();
    if (!res.ok) throw new Error(typeof data === "string" ? data : (Array.isArray(data.detail) ? data.detail.map(x => x.msg).join("; ") : data.detail || "Request failed"));
    return data;
  }
  function showLogin() { state.user = null; state.csrf = ""; workspace.hidden = true; loginPanel.hidden = false; $("#identity").hidden = true; }
  async function startSession(result) {
    state.user = result.user; state.csrf = result.csrf_token;
    loginPanel.hidden = true; workspace.hidden = false;
    const identity = $("#identity"); identity.hidden = false; identity.textContent = `${state.user.full_name} · ${state.user.role}`;
    $(".admin-only").hidden = !isRole("system_administrator");
    $(".audit-only").hidden = !isRole("system_administrator", "head_of_office");
    $("[data-view=analytics]").hidden = !isRole("head_of_office");
    $("[data-view=reports]").hidden = !isRole("head_of_office", "editor", "shift_leader");
    try { [state.people, state.shifts, state.departments] = await Promise.all([
      api("/api/people").catch(() => []), api("/api/shifts").catch(() => []), api("/api/departments").catch(() => [])
    ]); } catch (_) {}
    await showView(state.activeView || "dashboard");
  }
  function stats(items) {
    const count = status => items.filter(x => x.status === status).length;
    return `<div class="grid">
      <div class="card stat"><div class="label">Assigned to you</div><div class="value">${items.length}</div></div>
      <div class="card stat"><div class="label">In progress</div><div class="value">${count("In Progress")}</div></div>
      <div class="card stat"><div class="label">Submitted / review</div><div class="value">${count("Submitted") + count("Resubmitted") + count("Under Review")}</div></div>
      <div class="card stat"><div class="label">Verified</div><div class="value">${count("Verified")}</div></div></div>`;
  }
  async function loadDashboard() {
    const root = $("#view-dashboard");
    root.innerHTML = `<div class="page-heading"><div><h1>Office overview</h1><p>Live information from this office database.</p></div></div><div class="empty">Loading office information…</div>`;
    if (isRole("head_of_office")) {
      try {
        const d = await api("/api/reports/dashboard");
        const cards = [["Total staff", d.staff_total], ["Working today", d.staff_planned_today], ["Assigned today", d.tasks_assigned_today], ["In progress", d.in_progress], ["Submitted", d.submitted], ["Verified", d.verified], ["Overdue", d.overdue], ["Needs correction", d.correction_requested]];
        root.innerHTML = `<div class="page-heading"><div><h1>Management dashboard</h1><p>${esc(today())} · live operational counts</p></div></div><div class="grid">${cards.map(([n,v])=>`<div class="card stat"><div class="label">${n}</div><div class="value">${v}</div></div>`).join("")}</div><div class="panel"><h2>Weekly employee performance</h2>${performanceTable(d.weekly_performance || [])}</div>`;
      } catch (e) { root.innerHTML = `<div class="message error">${esc(e.message)}</div>`; }
      return;
    }
    if (isRole("timetable_planner")) {
      root.innerHTML = `<div class="page-heading"><div><h1>Timetable planning</h1><p>Prepare the coming week and track approval feedback.</p></div><button class="button primary" data-view="timetable">Open weekly timetable</button></div><div class="panel"><h2>Planning checklist</h2><p>Build the Monday-to-Sunday allocations, check each shift/editor/leader, then submit to the Head for review. Published schedules can only be changed with a new version and a reason.</p></div>`;
      return;
    }
    if (isRole("system_administrator")) {
      root.innerHTML = `<div class="page-heading"><div><h1>System administration</h1><p>Manage accounts, roles, shifts, and departments. Administrator access does not grant business approval permissions.</p></div></div><div class="panel"><h2>Getting started</h2><p>Use Accounts &amp; setup to create office user accounts. Business planning and review requires an assigned business role.</p></div>`;
      return;
    }
    try {
      const items = await api("/api/tasks");
      root.innerHTML = `<div class="page-heading"><div><h1>Hello, ${esc(state.user.full_name)}</h1><p>Your personal work summary · ${esc(today())}</p></div></div>${stats(items)}<div class="panel"><div class="panel-head"><h2>My current tasks</h2><button class="button small" data-view="tasks">Open tasks</button></div>${taskList(items.slice(0,6))}</div>`;
    } catch (e) { root.innerHTML = `<div class="message error">${esc(e.message)}</div>`; }
  }
  function performanceTable(rows) {
    if (!rows.length) return `<div class="empty">No assignments or task activity in this period yet.</div>`;
    return `<div class="table-wrap"><table><thead><tr><th>Employee</th><th>Planned shifts</th><th>Assigned</th><th>Submitted</th><th>Verified</th><th>Pending</th><th>Overdue</th><th>Submit %</th><th>Verified %</th><th>Exceptions</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.employee)}</td><td>${r.planned_shifts.map(x=>esc(x.date)+" · "+esc(x.shift)).join("<br>")||"—"}</td><td>${r.assigned}</td><td>${r.submitted}</td><td>${r.verified}</td><td>${r.pending}</td><td>${r.overdue}</td><td>${r.submission_rate}%</td><td>${r.verified_completion_rate}%</td><td>${esc((r.exceptions||[]).join("; ")||"—")}</td></tr>`).join("")}</tbody></table></div>`;
  }
  function chartRows(rows) {
    if (!rows.length) return `<p class="hint">No data.</p>`;
    const max=Math.max(1,...rows.map(r=>r.assigned));
    return `<div class="chart-list">${rows.slice(0,8).map(r=>`<div class="chart-row"><div class="chart-label"><span>${esc(r.label)}</span><b>${r.verified}/${r.assigned}</b></div><div class="bar-track"><span class="bar-submitted" style="width:${Math.min(100,r.submitted*100/max)}%"></span><span class="bar-verified" style="width:${Math.min(100,r.verified*100/max)}%"></span></div><small>${r.submission_rate}% submitted · ${r.verified_rate}% verified</small></div>`).join("")}</div>`;
  }
  function taskList(items) {
    if (!items.length) return `<div class="empty">No tasks to show.</div>`;
    const manager = isRole("head_of_office", "editor");
    return `<div class="task-list">${items.map(t=>`<article class="task-card"><div class="panel-head"><h3>${esc(t.title)}</h3><span class="badge ${esc(t.status.toLowerCase().replaceAll(" ","-"))}">${esc(t.status)}</span></div><div class="task-meta"><span>${esc(t.reference)}</span><span>For ${esc(t.employee || "you")}</span><span>Due ${esc(new Date(t.deadline).toLocaleString())}</span><span>${esc(t.priority)} priority</span></div><p>${esc(t.description || t.instructions || "No extra instructions.")}</p><div class="row-actions">${!manager && t.status === "Assigned" ? `<button class="button small" data-action="ack" data-id="${t.id}">Acknowledge</button>`:""}${!manager && ["Assigned","Acknowledged"].includes(t.status) ? `<button class="button small" data-action="start" data-id="${t.id}">Start work</button>`:""}${!manager && ["Assigned","Acknowledged","In Progress","Correction Requested","Rejected"].includes(t.status) ? `<button class="button small primary" data-action="submit" data-id="${t.id}">Submit work</button>`:""}${manager && ["Submitted","Resubmitted","Under Review"].includes(t.status) ? `<button class="button small primary" data-action="review" data-id="${t.id}">Review submission</button>`:""}${manager && !["Verified","Cancelled"].includes(t.status) ? `<button class="button small" data-action="task-edit" data-id="${t.id}" data-title="${esc(t.title)}" data-employee="${t.employee_id}" data-deadline="${localDateTime(t.deadline)}" data-priority="${t.priority}">Edit / reassign</button><button class="button small danger" data-action="task-cancel" data-id="${t.id}">Cancel task</button>`:""}<button class="button small" data-action="history" data-id="${t.id}">View submissions</button></div><div id="submissions-${t.id}"></div></article>`).join("")}</div>`;
  }
  function taskCreateForm() {
    const employees = state.people.filter(p=>["staff","shift_leader","editor","head_of_office"].includes(p.role_id));
    return `<div class="panel"><h2>Assign work</h2><form id="task-create" class="form-grid">
      <label>Task title<input name="title" maxlength="180" required></label><label>Priority<select name="priority"><option>Normal</option><option>Low</option><option>High</option><option>Urgent</option></select></label>
      <label class="wide">Description<textarea name="description"></textarea></label><label class="wide">Instructions<textarea name="instructions"></textarea></label>
      <label>Employees (Ctrl/Cmd to select multiple)<select name="employee_ids" multiple size="4" required>${employees.map(p=>`<option value="${p.id}">${esc(p.full_name)} · ${esc(p.role)}</option>`).join("")}</select></label>
      <label>Department<select name="department_id"><option value="">Not specified</option>${state.departments.map(d=>`<option value="${d.id}">${esc(d.name)}</option>`).join("")}</select></label>
      <label>Shift<select name="shift_id"><option value="">Not specified</option>${state.shifts.map(s=>`<option value="${s.id}">${esc(s.name)} (${s.start_time}–${s.end_time})</option>`).join("")}</select></label>
      <label>Deadline<input type="datetime-local" name="deadline" required></label><label>Assignment date<input type="date" name="assignment_date" value="${today()}" required></label><label>Start date<input type="date" name="start_date" value="${today()}" required></label>
      <div class="wide"><button class="button primary" type="submit">Create accountable task record(s)</button><span class="hint">Each selected employee gets an individual accountable task.</span></div></form></div>`;
  }
  async function loadTasks() {
    const root = $("#view-tasks"); root.innerHTML = `<div class="page-heading"><div><h1>Tasks</h1><p>Assignments, submissions, and review status.</p></div></div>`;
    if (isRole("system_administrator", "timetable_planner")) { root.innerHTML += `<div class="empty">Task assignment is a business permission. Sign in with an editor or head-of-office account to assign work.</div>`; return; }
    if (isRole("head_of_office", "editor")) root.innerHTML += taskCreateForm();
    try { const tasks = await api("/api/tasks"); root.innerHTML += `<div class="panel"><h2>${isRole("head_of_office","editor")?"Assigned task queue":"My tasks and responsibilities"}</h2>${taskList(tasks)}</div>`; }
    catch(e) { root.innerHTML += `<div class="message error">${esc(e.message)}</div>`; }
  }
  function assignmentForm(timetableId, weekStart) {
    return `<div class="panel"><h3>Add duty allocation</h3><form class="form-grid assignment-form" data-timetable="${timetableId}">
      <label>Date<input type="date" name="work_date" value="${weekStart}" required></label><label>Shift<select name="shift_id" required>${state.shifts.map(s=>`<option value="${s.id}">${esc(s.name)} ${s.start_time}–${s.end_time}</option>`).join("")}</select></label>
      <label>Employee<select name="employee_id" required>${state.people.map(p=>`<option value="${p.id}">${esc(p.full_name)} · ${esc(p.role)}</option>`).join("")}</select></label>
      <label>Shift leader<select name="leader_id"><option value="">None</option>${state.people.map(p=>`<option value="${p.id}">${esc(p.full_name)}</option>`).join("")}</select></label>
      <label>Editor<select name="editor_id"><option value="">None</option>${state.people.map(p=>`<option value="${p.id}">${esc(p.full_name)}</option>`).join("")}</select></label>
      <label>Department<select name="department_id"><option value="">None</option>${state.departments.map(d=>`<option value="${d.id}">${esc(d.name)}</option>`).join("")}</select></label>
      <label class="wide">Responsibility / timetable column<input name="responsibility" placeholder="Jambo / Asubuhi hii, Reporting, Mpira NBC, Jioni"></label>
      <div class="wide"><button class="button small primary" type="submit">Add allocation</button></div></form></div>`;
  }
  function timetableActions(t) {
    if (isRole("timetable_planner")) return `${t.status === "Draft" || t.status === "Returned for Correction" ? `<button class="button small primary" data-action="tt-submit" data-id="${t.id}">Submit for review</button>`:""}${t.status === "Published" ? `<button class="button small" data-action="tt-version" data-id="${t.id}">Create new version</button>`:""}`;
    if (isRole("head_of_office")) return `${["Draft","Returned for Correction"].includes(t.status) ? `<button class="button small primary" data-action="tt-submit" data-id="${t.id}">Submit for review</button>`:""}${["Submitted","Under Review"].includes(t.status) ? `<button class="button small" data-action="tt-review" data-id="${t.id}" data-decision="under_review">Begin review</button><button class="button small" data-action="tt-review" data-id="${t.id}" data-decision="return">Return</button><button class="button small primary" data-action="tt-review" data-id="${t.id}" data-decision="approve">Approve</button>`:""}${t.status === "Approved" ? `<button class="button small primary" data-action="tt-publish" data-id="${t.id}">Publish</button>`:""}${t.status === "Published" ? `<button class="button small" data-action="tt-version" data-id="${t.id}">Create new version</button>${t.week_end<today()?`<button class="button small" data-action="tt-archive" data-id="${t.id}">Archive</button>`:""}`:""}`;
    return "";
  }
  async function loadTimetable() {
    const root = $("#view-timetable"); root.innerHTML = `<div class="page-heading"><div><h1>Weekly timetable</h1><p>Published schedules are immutable. Corrections require a versioned update.</p></div></div>`;
    if (isRole("head_of_office", "timetable_planner")) root.innerHTML += `<div class="panel"><h2>Prepare a week</h2><form id="timetable-create" class="inline-form"><label>Monday of the week<input type="date" name="week_start" value="${monday()}" required></label><button class="button primary">Create draft</button><span class="hint">Copy a previous week using the copy control on its row.</span></form></div>`;
    try {
      const items = await api("/api/timetables");
      root.innerHTML += items.length ? items.map(t=>`<article class="panel"><div class="panel-head"><div><h2>Week ${esc(t.week_start)} – ${esc(t.week_end)} · v${t.version}</h2><span class="badge ${esc(t.status.toLowerCase().replaceAll(" ","-"))}">${esc(t.status)}</span> ${esc(t.approval_comment||"")}</div><div class="row-actions">${timetableActions(t)}${isRole("head_of_office","timetable_planner")?`<button class="button small" data-action="tt-copy" data-id="${t.id}">Copy to another week</button>`:""}</div></div><div class="table-wrap"><table><thead><tr><th>Date</th><th>Duty / column</th><th>Shift</th><th>Employee</th><th>Leader</th><th>Editor</th><th>Actions</th></tr></thead><tbody>${t.assignments.map(a=>`<tr><td>${esc(a.work_date)}</td><td>${esc(a.responsibility)}</td><td>${esc(a.shift)}</td><td>${esc(a.employee)}</td><td>${esc(a.leader||"—")}</td><td>${esc(a.editor||"—")}</td><td>${isRole("head_of_office","timetable_planner") && ["Draft","Returned for Correction","Submitted","Under Review"].includes(t.status)?`<button class="button small" data-action="tt-edit" data-assignment="${a.id}" data-timetable="${t.id}" data-date="${a.work_date}" data-shift="${a.shift_id}" data-employee="${a.employee_id}" data-leader="${a.leader_id||""}" data-editor="${a.editor_id||""}" data-dept="${a.department_id||""}" data-duty="${esc(a.responsibility)}">Edit</button><button class="button small danger" data-action="tt-delete" data-id="${a.id}" data-timetable="${t.id}">Remove</button>`:""}</td></tr>`).join("")}</tbody></table></div>${isRole("head_of_office","timetable_planner") && ["Draft","Returned for Correction","Submitted","Under Review"].includes(t.status)?assignmentForm(t.id,t.week_start):""}</article>`).join("") : `<div class="empty">No weekly schedules are available yet.</div>`;
    } catch(e) { root.innerHTML += `<div class="message error">${esc(e.message)}</div>`; }
  }
  async function loadShiftComparison(reportDate) {
    const target=$("#shift-comparison-results");if(!target)return;
    try {const data=await api(`/api/reports/shift-comparison?report_date=${encodeURIComponent(reportDate)}`);target.innerHTML=data.shifts.length?`<div class="table-wrap"><table><thead><tr><th>Shift</th><th>Assigned</th><th>Submitted</th><th>Verified</th><th>Pending</th><th>Overdue</th><th>Handover / unfinished</th><th>Challenges</th></tr></thead><tbody>${data.shifts.map(s=>`<tr><td>${esc(state.shifts.find(x=>x.id===s.shift_id)?.name||"Unspecified")}</td><td>${s.assigned}</td><td>${s.submitted}</td><td>${s.verified}</td><td>${s.pending}</td><td>${s.overdue}</td><td>${esc([s.report,s.unfinished].filter(Boolean).join(" · ")||"—")}</td><td>${esc(s.challenges||"—")}</td></tr>`).join("")}</tbody></table></div>`:`<div class="empty">No shift reports were submitted for this date.</div>`;}catch(e){target.innerHTML=`<div class="message error">${esc(e.message)}</div>`;}
  }
  async function loadReports() {
    const root = $("#view-reports");
    root.innerHTML = `<div class="page-heading"><div><h1>Shift handover reports</h1><p>Record incomplete responsibilities, challenges, attendance notes, and handover details.</p></div></div>`;
    if (isRole("head_of_office")) root.innerHTML += `<div class="panel"><h2>End-of-day shift comparison</h2><form id="shift-comparison-filter" class="inline-form"><label>Report date<input type="date" name="report_date" value="${today()}" required></label><button class="button">Compare shifts</button></form><div id="shift-comparison-results"></div></div>`;
    if (isRole("head_of_office","editor","shift_leader")) root.innerHTML += `<div class="panel"><h2>Submit shift report</h2><form id="shift-report" class="form-grid"><label>Date<input name="report_date" type="date" value="${today()}" required></label><label>Shift<select name="shift_id"><option value="">Not specified</option>${state.shifts.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join("")}</select></label><label class="wide">Unfinished responsibilities<textarea name="unfinished"></textarea></label><label class="wide">Challenges<textarea name="challenges"></textarea></label><label class="wide">Attendance / absence notes<textarea name="attendance_notes"></textarea></label><label class="wide">Handover notes<textarea name="handover"></textarea></label><div class="wide"><button class="button primary">Submit shift report</button></div></form></div>`;
    try { const rows=await api("/api/shift-reports"); root.innerHTML += `<div class="panel"><h2>Recent reports</h2>${rows.length?`<div class="table-wrap"><table><thead><tr><th>Date</th><th>Shift</th><th>Submitted by</th><th>Unfinished / challenges</th><th>Handover</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.date)}</td><td>${esc(state.shifts.find(s=>s.id===r.shift_id)?.name||"—")}</td><td>${esc(r.submitted_by)}</td><td>${esc([r.unfinished,r.challenges,r.attendance_notes].filter(Boolean).join(" · "))}</td><td>${esc(r.handover)}</td></tr>`).join("")}</tbody></table></div>`:`<div class="empty">No handover reports yet.</div>`}</div>`; }
    catch(e) { root.innerHTML += `<div class="message error">${esc(e.message)}</div>`; }
    if (isRole("head_of_office")) await loadShiftComparison(today());
  }
  async function loadAnalytics() {
    const root=$("#view-analytics"); const start=new Date(); start.setDate(start.getDate()-((start.getDay()+6)%7));
    const startValue=start.toISOString().slice(0,10);
    root.innerHTML=`<div class="page-heading"><div><h1>Performance &amp; planned vs actual</h1><p>Submission and verified completion are different measures.</p></div></div><div class="panel"><form id="performance-filter" class="inline-form"><label>From<input type="date" name="start" value="${startValue}" required></label><label>To<input type="date" name="end" value="${today()}" required></label><button class="button primary">Run report</button></form><div id="performance-results"></div></div><div class="panel"><h2>Attendance, leave &amp; reassignment record</h2><form id="attendance-create" class="form-grid"><label>Employee<select name="employee_id" required>${state.people.map(p=>`<option value="${p.id}">${esc(p.full_name)}</option>`).join("")}</select></label><label>Date<input name="work_date" type="date" value="${today()}" required></label><label>Status<select name="status"><option>Present</option><option>Absent</option><option>Leave</option><option>Reassigned</option></select></label><label>Reason<input name="reason" maxlength="5000"></label><div class="wide"><button class="button">Save approved exception</button></div></form><p class="hint">Use this to record an authorized absence, leave or reassignment so planned-vs-actual reporting has context.</p></div>`;
    await runPerformance(startValue,today());
  }
  async function runPerformance(start,end) {
    const target=$("#performance-results"); if (!target) return;
    try { const data=await api(`/api/reports/performance?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
      const analytics=await api(`/api/reports/analytics?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
      const panels=[["By day",analytics.by_day],["By week",analytics.by_week],["By month",analytics.by_month],["By employee",analytics.by_employee],["By editor",analytics.by_editor],["By department",analytics.by_department],["By shift",analytics.by_shift]];
      target.innerHTML=`<div class="row-actions export-links"><a class="button small" href="/api/reports/tasks.pdf?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}">Download PDF</a><a class="button small" href="/api/reports/tasks.xlsx?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}">Download Excel</a><a class="button small" href="/api/reports/tasks.csv?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}">Download CSV</a></div>${performanceTable(data.employees)}<div class="grid report-breakdowns">${panels.map(([title,rows])=>`<div class="panel"><h3>${title}</h3>${chartRows(rows)}</div>`).join("")}</div>`;
    } catch(e) { target.innerHTML=`<div class="message error">${esc(e.message)}</div>`; }
  }
  async function loadAccounts() {
    const root=$("#view-accounts");
    if (!isRole("system_administrator")) { root.innerHTML=`<div class="message error">Administrator role required.</div>`; return; }
    const roles=await api("/api/roles").catch(()=>[]);
    root.innerHTML=`<div class="page-heading"><div><h1>Accounts &amp; office setup</h1><p>Administrative account and reference-data controls.</p></div></div>
    <div class="panel"><h2>Create user account</h2><form id="user-create" class="form-grid"><label>Username<input name="username" pattern="[A-Za-z0-9._-]+" required></label><label>Full name<input name="full_name" required></label><label>Initial password<input name="password" type="password" minlength="12" required></label><label>Role<select name="role_id">${roles.map(r=>`<option value="${r.id}">${esc(r.name)}</option>`).join("")}</select></label><label>Department<select name="department_id"><option value="">None</option>${state.departments.map(d=>`<option value="${d.id}">${esc(d.name)}</option>`).join("")}</select></label><div class="wide"><button class="button primary">Create account</button></div></form></div>
    <div class="panel"><h2>Departments &amp; shifts</h2><form id="department-create" class="inline-form"><label>New department<input name="name" required></label><button class="button">Add department</button></form><form id="shift-create" class="inline-form"><label>Shift name<input name="name" required></label><label>Starts<input name="start_time" type="time" value="08:00" required></label><label>Ends<input name="end_time" type="time" value="16:00" required></label><button class="button">Add shift</button></form></div>
    <div class="panel"><h2>Accounts</h2><div id="accounts-list">Loading…</div></div>`;
    try {const users=await api("/api/users"); $("#accounts-list").innerHTML=`<div class="table-wrap"><table><thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Department</th><th>Status</th><th></th></tr></thead><tbody>${users.map(u=>`<tr><td>${esc(u.full_name)}</td><td>${esc(u.username)}</td><td><select class="account-role" data-id="${u.id}">${roles.map(r=>`<option value="${r.id}" ${r.id===u.role_id?"selected":""}>${esc(r.name)}</option>`).join("")}</select></td><td><select class="account-dept" data-id="${u.id}"><option value="">None</option>${state.departments.map(d=>`<option value="${d.id}" ${d.id===u.department_id?"selected":""}>${esc(d.name)}</option>`).join("")}</select></td><td>${u.active?"Active":"Disabled"}</td><td><button class="button small" data-action="user-role" data-id="${u.id}">Save role/dept</button> <button class="button small" data-action="user-active" data-id="${u.id}" data-active="${!u.active}">${u.active?"Disable":"Enable"}</button> <button class="button small" data-action="user-reset" data-id="${u.id}">Reset password</button></td></tr>`).join("")}</tbody></table></div>`;}
    catch(e) { $("#accounts-list").textContent=e.message; }
  }
  async function loadAudit() {
    const root=$("#view-audit"); root.innerHTML=`<div class="page-heading"><div><h1>Audit history</h1><p>Recent recorded changes and access events.</p></div></div>`;
    try {const rows=await api("/api/audit?limit=200"); root.innerHTML+=`<div class="panel table-wrap"><table><thead><tr><th>Time</th><th>Actor ID</th><th>Action</th><th>Record</th><th>Details</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.created_at.replace("T"," "))}</td><td>${esc(r.actor_id)}</td><td>${esc(r.action)}</td><td>${esc(r.entity_type)} #${esc(r.entity_id)}</td><td>${esc(JSON.stringify(r.details))}</td></tr>`).join("")}</tbody></table></div>`;}
    catch(e){root.innerHTML+=`<div class="message error">${esc(e.message)}</div>`;}
  }
  async function showView(name) {
    state.activeView=name;
    $$(".view").forEach(v=>v.hidden=v.id!==`view-${name}`);
    $$(".nav-button").forEach(b=>b.classList.toggle("active",b.dataset.view===name));
    const loaders={dashboard:loadDashboard,tasks:loadTasks,timetable:loadTimetable,reports:loadReports,analytics:loadAnalytics,accounts:loadAccounts,audit:loadAudit};
    if (loaders[name]) await loaders[name]();
  }
  async function loadSubmissions(taskId) {
    const target=$(`#submissions-${taskId}`); if(!target) return;
    try {const rows=await api(`/api/tasks/${taskId}/submissions`); target.innerHTML=rows.length?rows.map(s=>`<div class="panel"><h3>Submission · ${esc(s.created_at.replace("T"," "))}</h3><p>${esc(s.report)}</p>${s.notes?`<p class="hint">${esc(s.notes)}</p>`:""}<div class="row-actions">${s.attachments.map(a=>`<a class="button small" href="/api/attachments/${a.id}">${esc(a.name)}</a>`).join("")}</div>${isRole("head_of_office","editor") && s.reviewable?`<div class="row-actions"><button class="button small primary" data-action="verify" data-id="${s.id}" data-decision="approve">Verify</button><button class="button small" data-action="verify" data-id="${s.id}" data-decision="request_correction">Request correction</button><button class="button small danger" data-action="verify" data-id="${s.id}" data-decision="reject">Reject</button></div>`:""}</div>`).join(""):`<p class="hint">No submissions yet.</p>`;}
    catch(e){target.innerHTML=`<div class="message error">${esc(e.message)}</div>`;}
  }
  document.addEventListener("click", async event => {
    const nav=event.target.closest("[data-view]"); if(nav){event.preventDefault(); await showView(nav.dataset.view); return;}
    const button=event.target.closest("[data-action]"); if(!button)return;
    const {action,id}=button.dataset;
    try {
      if(action==="ack") await api(`/api/tasks/${id}/acknowledge`,{method:"POST"});
      else if(action==="task-edit") {const people=state.people.map(p=>`${p.id}: ${p.full_name}`).join("; ");const title=prompt("Task title:",button.dataset.title);if(title===null)return;const employee=prompt(`Assigned employee ID (${people}; leave blank to keep current)`,"");const deadline=prompt("Deadline (YYYY-MM-DDTHH:MM):",button.dataset.deadline);if(deadline===null)return;const priority=prompt("Priority: Low, Normal, High, Urgent",button.dataset.priority);if(priority===null)return;const reason=prompt("Reason for this change:");if(!reason)return;const body={title,deadline:new Date(deadline).toISOString(),priority,reason};if(employee)body.employee_id=Number(employee);await api(`/api/tasks/${id}`,{method:"PATCH",body});}
      else if(action==="task-cancel") {const reason=prompt("Reason for cancelling this task:");if(!reason)return;await api(`/api/tasks/${id}/cancel`,{method:"POST",body:new URLSearchParams({reason})});}
      else if(action==="start") await api(`/api/tasks/${id}/start`,{method:"POST"});
      else if(action==="submit") { const report=window.prompt("Write a completion report:"); if(!report)return; const notes=window.prompt("Supporting notes (optional):")||""; const fd=new FormData();fd.append("report",report);fd.append("notes",notes); const input=document.createElement("input");input.type="file";input.multiple=true;input.accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx"; await new Promise(resolve=>{input.onchange=async()=>{for(const f of input.files)fd.append("files",f);try{await api(`/api/tasks/${id}/submit`,{method:"POST",body:fd});resolve();}catch(e){message(e.message,"error");resolve();}};input.oncancel=async()=>{try{await api(`/api/tasks/${id}/submit`,{method:"POST",body:fd});resolve();}catch(e){message(e.message,"error");resolve();}};input.click();});
      } else if(action==="history") {await loadSubmissions(id);return;}
      else if(action==="review") {const task=(await api("/api/tasks")).find(x=>x.id===Number(id));if(task && ["Submitted","Resubmitted"].includes(task.status))await api(`/api/tasks/${id}/start-review`,{method:"POST"});await loadSubmissions(id);return;}
      else if(action==="verify") {const comment=window.prompt("Reviewer comment:")||""; await api(`/api/submissions/${id}/verify`,{method:"POST",body:{decision:button.dataset.decision,comment}});}
      else if(action==="tt-submit") await api(`/api/timetables/${id}/submit`,{method:"POST"});
      else if(action==="tt-delete") {if(!confirm("Remove this assignment from the editable timetable?"))return;await api(`/api/timetables/${button.dataset.timetable}/assignments/${id}`,{method:"DELETE"});}
      else if(action==="tt-review") {const comment=window.prompt("Review note / correction reason (required for return):")||""; await api(`/api/timetables/${id}/review`,{method:"POST",body:new URLSearchParams({decision:button.dataset.decision,comment})});}
      else if(action==="tt-publish") {if(!confirm("Publish this approved timetable?"))return;await api(`/api/timetables/${id}/publish`,{method:"POST"});}
      else if(action==="tt-archive") {if(!confirm("Archive this completed published week?"))return;await api(`/api/timetables/${id}/archive`,{method:"POST"});}
      else if(action==="tt-version") {const reason=prompt("Reason for creating this revised published timetable:");if(!reason)return;await api(`/api/timetables/${id}/new-version`,{method:"POST",body:new URLSearchParams({reason})});}
      else if(action==="tt-edit") {const people=state.people.map(p=>`${p.id}: ${p.full_name}`).join("; ");const shifts=state.shifts.map(s=>`${s.id}: ${s.name} ${s.start_time}-${s.end_time}`).join("; ");const employee_id=Number(prompt(`Employee ID (${people})`,button.dataset.employee));if(!employee_id)return;const shift_id=Number(prompt(`Shift ID (${shifts})`,button.dataset.shift));if(!shift_id)return;const work_date=prompt("Duty date (YYYY-MM-DD)",button.dataset.date);if(!work_date)return;const leader_id=prompt(`Shift leader ID (${people}; blank for none)`,button.dataset.leader)||null;const editor_id=prompt(`Editor ID (${people}; blank for none)`,button.dataset.editor)||null;const responsibility=prompt("Timetable responsibility",button.dataset.duty)||"";const reason=prompt("Reason for changing this allocation:");if(!reason)return;await api(`/api/timetables/${button.dataset.timetable}/assignments/${button.dataset.assignment}`,{method:"PUT",body:{work_date,shift_id,employee_id,leader_id:leader_id?Number(leader_id):null,editor_id:editor_id?Number(editor_id):null,department_id:button.dataset.dept?Number(button.dataset.dept):null,responsibility,reason}}); }
      else if(action==="tt-copy") {const week=prompt("Enter the Monday date for the copied week (YYYY-MM-DD):");if(!week)return;await api(`/api/timetables/${id}/copy`,{method:"POST",body:{week_start:week}});}
      else if(action==="user-role") {const row=button.closest("tr");const role_id=$(".account-role",row).value;const department_id=$(".account-dept",row).value;await api(`/api/users/${id}`,{method:"PATCH",body:{role_id,department_id:department_id?Number(department_id):null}});}
      else if(action==="user-active") await api(`/api/users/${id}/active?active=${button.dataset.active}`,{method:"PATCH"});
      else if(action==="user-reset") { const password=prompt("Enter a temporary password of at least 12 characters. Share it securely with the user."); if(!password)return; const form=new URLSearchParams({password}); await api(`/api/users/${id}/reset-password`,{method:"POST",body:form}); }
      message("Saved successfully.","success"); await showView(state.activeView);
    } catch(e){message(e.message,"error");}
  });
  document.addEventListener("submit", async event=>{
    const form=event.target; event.preventDefault(); const fd=new FormData(form);
    try {
      if(form.id==="login-form") {
        if(!state.csrf) state.csrf=(await api("/api/auth/csrf")).csrf_token;
        const result=await api("/api/auth/login",{method:"POST",body:fd}); $("#login-error").hidden=true; await startSession(result); return;
      }
      if(form.id==="task-create") {
        const employeeIds=$$("select[name=employee_ids] option:checked",form).map(o=>Number(o.value));
        const body={title:fd.get("title"),description:fd.get("description"),instructions:fd.get("instructions"),employee_ids:employeeIds,
          department_id:fd.get("department_id")?Number(fd.get("department_id")):null,shift_id:fd.get("shift_id")?Number(fd.get("shift_id")):null,
          assignment_date:fd.get("assignment_date"),start_date:fd.get("start_date"),deadline:new Date(fd.get("deadline")).toISOString(),priority:fd.get("priority")};
        await api("/api/tasks",{method:"POST",body}); message("Individual task record(s) assigned.","success"); await loadTasks(); return;
      }
      if(form.id==="timetable-create") {const result=await api("/api/timetables",{method:"POST",body:{week_start:fd.get("week_start")}});message(`Draft created (version ${result.version}).`,"success");await loadTimetable();return;}
      if(form.classList.contains("assignment-form")) {
        const body={work_date:fd.get("work_date"),shift_id:Number(fd.get("shift_id")),employee_id:Number(fd.get("employee_id")),
          leader_id:fd.get("leader_id")?Number(fd.get("leader_id")):null,editor_id:fd.get("editor_id")?Number(fd.get("editor_id")):null,
          department_id:fd.get("department_id")?Number(fd.get("department_id")):null,responsibility:fd.get("responsibility")};
        await api(`/api/timetables/${form.dataset.timetable}/assignments`,{method:"POST",body});message("Duty allocation added.","success");await loadTimetable();return;
      }
      if(form.id==="shift-comparison-filter"){await loadShiftComparison(fd.get("report_date"));return;}
      if(form.id==="shift-report") {const body={report_date:fd.get("report_date"),shift_id:fd.get("shift_id")?Number(fd.get("shift_id")):null,unfinished:fd.get("unfinished"),challenges:fd.get("challenges"),handover:fd.get("handover"),attendance_notes:fd.get("attendance_notes")};await api("/api/shift-reports",{method:"POST",body});message("Shift handover report submitted.","success");await loadReports();return;}
      if(form.id==="performance-filter"){await runPerformance(fd.get("start"),fd.get("end"));return;}
      if(form.id==="attendance-create"){await api("/api/attendance",{method:"POST",body:{employee_id:Number(fd.get("employee_id")),work_date:fd.get("work_date"),status:fd.get("status"),reason:fd.get("reason")}});message("Attendance record saved.","success");const filter=$("#performance-filter");if(filter)await runPerformance(filter.elements.start.value,filter.elements.end.value);return;}
      if(form.id==="user-create"){const body={username:fd.get("username"),full_name:fd.get("full_name"),password:fd.get("password"),role_id:fd.get("role_id"),department_id:fd.get("department_id")?Number(fd.get("department_id")):null};await api("/api/users",{method:"POST",body});message("Account created. Provide initial password securely.","success");await loadAccounts();return;}
      if(form.id==="department-create"){await api("/api/departments",{method:"POST",body:{name:fd.get("name")}});[state.departments]=await Promise.all([api("/api/departments")]);message("Department created.","success");await loadAccounts();return;}
      if(form.id==="shift-create"){await api("/api/shifts",{method:"POST",body:{name:fd.get("name"),start_time:fd.get("start_time"),end_time:fd.get("end_time")}});state.shifts=await api("/api/shifts");message("Shift created.","success");await loadAccounts();return;}
    } catch(e) {
      if(form.id==="login-form"){const error=$("#login-error");error.textContent=e.message;error.hidden=false;} else message(e.message,"error");
    }
  });
  $("#password-button").addEventListener("click",async()=>{const current_password=prompt("Current password:");if(!current_password)return;const new_password=prompt("New password (at least 12 characters):");if(!new_password)return;try{await api("/api/auth/change-password",{method:"POST",body:new URLSearchParams({current_password,new_password})});message("Password changed. Sign in again.","success");showLogin();}catch(e){message(e.message,"error");}});
  $("#logout-button").addEventListener("click",async()=>{try{await api("/api/auth/logout",{method:"POST"});}catch(_){}showLogin();});
  api("/api/auth/me").then(startSession).catch(()=>showLogin());
})();
