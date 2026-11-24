(() => {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const state = { user: null, csrf: "", people: [], shifts: [], departments: [], socialAllowed: false, socialOfficerUsers: [], socialAccounts: [], socialPreviewFile: null, activeView: "dashboard" };
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
    const socialAccess = await api("/api/social/access").catch(() => ({allowed:false}));
    state.socialAllowed = Boolean(socialAccess.allowed);
    $(".social-only").hidden = !state.socialAllowed;
    if (!state.socialAllowed && state.activeView === "social") state.activeView = "dashboard";
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
    const employeeHint=isRole("editor")?"Editors see staff assigned to them on published timetables for the next seven days and may assign only on the matching roster date. If this list is empty, ask the Head to publish a timetable with your editor assignment, then sign out and back in.":"Create active employee accounts before assigning tasks.";
    const employeePicker=`<label>Employees (Ctrl/Cmd to select multiple)<select name="employee_ids" multiple size="4" required ${employees.length?"":"disabled"}>${employees.map(p=>`<option value="${p.id}">${esc(p.full_name)} · ${esc(p.role)}</option>`).join("")}</select><span class="hint">${employees.length?isRole("editor")?employeeHint:"Select active staff accounts.":employeeHint}</span></label>`;
    return `<div class="panel"><h2>Assign work</h2><form id="task-create" class="form-grid">
      <label>Task title<input name="title" maxlength="180" required></label><label>Priority<select name="priority"><option>Normal</option><option>Low</option><option>High</option><option>Urgent</option></select></label>
      <label class="wide">Description<textarea name="description"></textarea></label><label class="wide">Instructions<textarea name="instructions"></textarea></label>
      ${employeePicker}
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
  const SOCIAL_PLATFORMS = [["youtube","YouTube"],["facebook","Facebook"],["instagram","Instagram"],["x","X"],["tiktok","TikTok"]];
  const SOCIAL_METRICS = [["audience_start","Audience/followers at start"],["audience_end","Audience/followers at end"],
    ["new_followers","New followers/subscribers"],["lost_followers","Lost followers"],["reach","Reach"],["impressions","Impressions"],
    ["views","Views"],["likes","Likes"],["comments","Comments"],["shares","Shares"],["saves","Saves"],
    ["posts_published","Posts published"],["videos_published","Videos published"]];
  const socialMonday = (value=today()) => {const d=new Date(`${value}T12:00:00`);d.setDate(d.getDate()-((d.getDay()+6)%7));return d.toISOString().slice(0,10);};
  const socialValue = value => value===null||value===undefined?"N/A":String(value);
  const socialPercent = value => value===null||value===undefined?"N/A":`${value}%`;
  function socialMetricFields(values={}) {
    return `<div class="social-metric-grid">${SOCIAL_METRICS.map(([key,label])=>`<label>${label}<input name="${key}" type="text" inputmode="numeric" pattern="(N/A|[0-9]+)" value="${esc(socialValue(values[key]))}" placeholder="N/A or whole number" aria-label="${label}; enter N/A when unavailable" required></label>`).join("")}</div>`;
  }
  function socialWeeklyForm(platform, accountId, report=null) {
    const id=report?`social-edit-${report.id}`:`social-create-${accountId}`;
    const week=report?.reporting_week||socialMonday();
    return `<form id="${id}" class="social-report-form" data-platform="${platform}" data-account="${report?.account_id||accountId}" data-report="${report?.id||""}">
      <div class="form-grid"><label>Reporting date<input name="reporting_date" type="date" value="${report?.reporting_date||today()}" required></label>
      <label>Reporting week (Monday start)<input name="reporting_week" type="date" value="${week}" required></label>
      <label class="wide">Statistics <span class="hint">Enter a whole number including 0, or leave the explicit N/A marker. A blank or unavailable statistic is never silently treated as zero.</span></label>
      <div class="wide">${socialMetricFields(report?.metrics||{})}</div>
      <label class="wide">Best-performing content<textarea name="best_content" maxlength="5000">${esc(report?.best_content||"")}</textarea></label>
      <label class="wide">Comments and recommendations<textarea name="recommendations" maxlength="10000">${esc(report?.recommendations||"")}</textarea></label>
      <label class="wide">Supporting screenshots / PDF / Excel / CSV ${report?"(add more evidence)":"(recommended; required before submission)"}<input name="evidence" type="file" multiple accept="image/png,image/jpeg,application/pdf,.xlsx,.csv"></label>
      <div class="wide"><button class="button primary">${report?"Save corrected draft":"Save weekly draft"}</button></div></div>
      <p class="hint">Source is recorded as Manually entered. No social login credentials or external API are used.</p></form>`;
  }
  function socialAccountsMarkup() {
    return `<div class="panel"><h2>Official platform accounts</h2><p class="hint">Register every real, verified office profile. Weekly reports and quarterly totals remain separate for each account. The module never asks for platform passwords or API tokens.</p><div class="grid social-platform-grid">${SOCIAL_PLATFORMS.map(([platform,label])=>{
      const accounts=state.socialAccounts.filter(a=>a.platform===platform);
      return `<section class="social-account-card"><h3>${esc(label)} · ${accounts.length} account(s)</h3>${accounts.map(a=>`<details><summary>${esc(a.account_handle||"Account details required")}</summary>
        <form id="social-account-edit-${a.id}" class="form-grid"><label>Official profile/display name<input name="account_name" value="${esc(a.account_name||"")}" required maxlength="160"></label>
        <label>Verified handle / channel identifier<input name="account_handle" value="${esc(a.account_handle||"")}" required maxlength="160"></label>
        <label class="wide">Public profile URL (optional)<input name="profile_url" type="url" value="${esc(a.profile_url||"")}" placeholder="https://..."></label>
        <div class="wide"><button class="button">Update verified profile</button></div></form></details>`).join("")}
        <details><summary>Add another ${esc(label)} account</summary><form id="social-account-create-${platform}" class="form-grid" data-platform="${platform}">
        <label>Official profile/display name<input name="account_name" required maxlength="160"></label><label>Verified handle / channel identifier<input name="account_handle" required maxlength="160"></label>
        <label class="wide">Public profile URL (optional)<input name="profile_url" type="url" placeholder="https://..."></label><div class="wide"><button class="button">Register ${esc(label)} account</button></div></form></details></section>`;
    }).join("")}</div></div>`;
  }
  async function loadSocial() {
    const root=$("#view-social");
    if(!state.socialAllowed){root.innerHTML=`<div class="message error">Designated social media officer or Head of Office permission required.</div>`;return;}
    root.innerHTML=`<div class="page-heading"><div><h1>TBC Digital social media performance</h1><p>Manual-first reporting for YouTube, Facebook, Instagram, X and TikTok. Works without API credentials, integrations, scraping, or storing social passwords.</p></div></div><div class="empty">Loading social media records…</div>`;
    try {
      const [accounts,reports,quarters]=await Promise.all([api("/api/social/accounts"),api("/api/social/weekly"),api("/api/social/quarters")]);
      state.socialAccounts=accounts; state.socialReports=reports; state.socialQuarters=quarters;
      let setup="";
      if(isRole("head_of_office")){
        const config=await api("/api/social/officers");
        setup=`${socialAccountsMarkup()}<div class="panel"><h2>Designate social media reporting officers</h2><form id="social-officers"><div class="form-grid">${config.users.map(u=>`<label class="social-check"><input type="checkbox" name="user_ids" value="${u.id}" ${config.user_ids.includes(u.id)?"checked":""}>${esc(u.name)} · ${esc(u.role)}</label>`).join("")||"<p>No active eligible user accounts.</p>"}<div class="wide"><button class="button">Save designated officers</button></div></div></form><p class="hint">Only designated officers enter and submit weekly/quarterly reports. The Head reviews and approves; self-approval is blocked.</p></div>`;
      }
      const accountCards=SOCIAL_PLATFORMS.map(([platform,label])=>{
        const platformAccounts=accounts.filter(a=>a.platform===platform&&a.configured);
        return platformAccounts.length?platformAccounts.map(account=>`<details class="panel social-entry"><summary><strong>${esc(label)}</strong> · ${esc(account.account_handle)}</summary>
          ${socialWeeklyForm(platform,account.id)}</details>`).join(""):
          `<details class="panel social-entry"><summary><strong>${esc(label)}</strong> · Register verified account profile first</summary><p class="hint">The Head of Office must enter and verify at least one official profile before statistics can be recorded.</p></details>`;
      }).join("");
      const reportList=socialReportTable(reports);
      const importPanel=`<div class="panel"><h2>Import from Excel or CSV</h2><p>Download a blank template, fill one row per account-week and enter its configured account_handle, mark unavailable fields N/A, preview validation, correct errors in the file and preview again. Successful imports are saved as Draft, marked Imported from file, and the original file is attached as evidence.</p>
        <div class="row-actions"><a class="button small" href="/api/social/template.xlsx">Download Excel template</a><a class="button small" href="/api/social/template.csv">Download CSV template</a></div>
        <form id="social-import" class="inline-form"><label>Analytics data file<input type="file" name="file" accept=".xlsx,.csv" required></label><button class="button">Validate and preview</button></form><div id="social-import-preview"></div></div>`;
      const reportsPanel=`<div class="panel"><div class="panel-head"><div><h2>Weekly reports</h2><p class="hint">${reports.length} saved report record(s), including drafts, returned reports and approvals.</p></div><div class="row-actions export-links"><a class="button small" href="/api/social/exports.pdf">Export PDF</a><a class="button small" href="/api/social/exports.xlsx">Export Excel</a></div></div>
        <form id="social-weekly-filter" class="inline-form"><label>From week<input type="date" name="start"></label><label>To week<input type="date" name="end"></label><label>Platform<select name="platform"><option value="">All five</option>${SOCIAL_PLATFORMS.map(([p,n])=>`<option value="${p}">${n}</option>`).join("")}</select></label><label>Account<select name="account_id"><option value="">All accounts</option>${accounts.filter(a=>a.configured).map(a=>`<option value="${a.id}">${esc(a.platform_name)} · ${esc(a.account_handle)}</option>`).join("")}</select></label><button class="button">Filter</button></form><div id="social-weekly-list">${reportList}</div></div>`;
      const qNow=new Date(); const year=qNow.getFullYear(); const quarter=Math.floor(qNow.getMonth()/3)+1;
      const quarterlyPanel=`<div class="panel"><h2>Quarterly management reports</h2><p class="hint">Quarterly reports consolidate approved weekly records separately per registered account—no duplicate re-entry or cross-account blending. They preserve a snapshot and list source weekly report IDs, coverage, N/A totals and calculation methodology. Empty/unreported accounts remain N/A.</p>
        <form id="social-quarter-generate" class="inline-form"><label>Year<input name="year" type="number" min="2000" max="2200" value="${year}" required></label><label>Quarter<select name="quarter">${[1,2,3,4].map(n=>`<option value="${n}" ${n===quarter?"selected":""}>Q${n}</option>`).join("")}</select></label><button class="button primary">Generate / refresh draft from approved weeks</button></form><div id="social-quarter-list">${socialQuarterCards(quarters)}</div></div>`;
      const start=new Date();start.setDate(start.getDate()-90); const startValue=start.toISOString().slice(0,10);
      const analyticsPanel=`<div class="panel"><h2>Performance graphs from approved saved data</h2><p class="hint">Filters use actual approved weekly records. Choose week, month or quarter to view growth in that period. Missing metrics remain N/A.</p>
        <form id="social-analytics-filter" class="inline-form"><label>From<input type="date" name="start" value="${startValue}" required></label><label>To<input type="date" name="end" value="${today()}" required></label>
        <label>Platform<select name="platform"><option value="">All platforms</option>${SOCIAL_PLATFORMS.map(([p,n])=>`<option value="${p}">${n}</option>`).join("")}</select></label>
        <label>Growth period<select name="grain"><option value="week">Weekly</option><option value="month">Monthly</option><option value="quarter">Quarterly</option></select></label><button class="button primary">Refresh graphs</button></form>
        <p id="social-engagement-method" class="hint"></p><div id="social-graphs" class="social-graphs"></div></div>`;
      root.innerHTML=`<div class="page-heading"><div><h1>TBC Digital social media performance</h1><p>Weekly officer entry → Head review → quarterly consolidation and management approval.</p></div></div>${setup}<div class="panel"><h2>Weekly statistics by platform</h2><p class="hint">Each platform has its own reporting form. All metric fields start as N/A—not zero. Enter 0 only when the platform actually reports zero.</p>${accountCards}</div>${reportsPanel}${importPanel}${quarterlyPanel}${analyticsPanel}`;
      await refreshSocialWeekly(); await refreshSocialAnalytics(startValue,today(),"","week");
    } catch(e){root.innerHTML=`<div class="message error">${esc(e.message)}</div>`;}
  }
  function socialQuarterCards(rows) {
    if(!rows.length)return `<div class="empty">No quarterly reports generated yet.</div>`;
    return rows.map(q=>`<article class="task-card"><div class="panel-head"><h3>Q${q.quarter} ${q.year}</h3><span class="badge">${esc(q.status)}</span></div>
      <p>${q.snapshot.approved_weekly_report_count} approved weekly report(s) consolidated · generated by ${esc(q.generated_by)} · ${esc(q.generated_at)}</p>
      <p class="hint">${esc(q.snapshot.method)}<br><b>Engagement method:</b> ${esc(q.snapshot.engagement_formula)}</p>${q.management_notes?`<p><b>Management analysis/recommendations:</b> ${esc(q.management_notes)}</p>`:""}${q.review_comment?`<p><b>Management review:</b> ${esc(q.review_comment)}</p>`:""}
      <details class="panel"><summary>Weekly best content and recommendations consolidated</summary>${q.snapshot.platforms.map(p=>`<h4>${esc(p.platform_name)} ${esc(p.account_handle||"")}</h4>${p.weekly_narratives.map(n=>`<p><b>${esc(n.reporting_week)} · report ${esc(n.report_id)}</b><br>Best content: ${esc(n.best_content||"N/A")}<br>Recommendations: ${esc(n.recommendations||"N/A")}</p>`).join("")||"<p>N/A</p>"}`).join("")}</details><div class="table-wrap"><table><thead><tr><th>Platform</th><th>Weeks</th><th>Audience start → end</th><th>Net growth</th><th>Growth %</th><th>Reach</th><th>Views</th><th>Engagement %</th><th>Posts / videos</th><th>Source report IDs</th></tr></thead><tbody>${q.snapshot.platforms.map(p=>`<tr><td>${esc(p.platform_name)} ${esc(p.account_handle||"")}</td><td>${p.weeks_reported}</td><td>${socialValue(p.audience_start)} → ${socialValue(p.audience_end)}</td><td>${socialValue(p.net_follower_growth)}</td><td>${socialPercent(p.audience_growth_percent)}</td><td>${socialValue(p.reach)}</td><td>${socialValue(p.views)}</td><td>${socialPercent(p.engagement_rate_percent)}</td><td>${socialValue(p.posts_published)} / ${socialValue(p.videos_published)}</td><td>${p.weekly_report_ids.map(esc).join(", ")||"N/A"}</td></tr>`).join("")}</tbody></table></div>
      ${["Draft","Returned for Correction","Rejected"].includes(q.status)?`<form id="social-quarter-edit-${q.id}" class="form-grid"><label class="wide">Quarterly management analysis / recommendations<textarea name="management_notes" maxlength="20000">${esc(q.management_notes||"")}</textarea></label><div class="wide"><button class="button">Save analysis</button><button type="button" class="button primary" data-social-action="submit-quarter" data-id="${q.id}">Submit quarter for approval</button></div></form>`:""}
      ${isRole("head_of_office")&&q.status==="Submitted"?`<div class="row-actions"><button class="button small primary" data-social-action="review-quarter" data-decision="approve" data-id="${q.id}">Approve quarter</button><button class="button small" data-social-action="review-quarter" data-decision="correction" data-id="${q.id}">Request correction</button><button class="button small danger" data-social-action="review-quarter" data-decision="reject" data-id="${q.id}">Reject quarter</button></div>`:""}
      <div class="row-actions"><a class="button small" href="/api/social/quarters/${q.id}/exports.pdf">Download quarter PDF</a><a class="button small" href="/api/social/quarters/${q.id}/exports.xlsx">Download quarter Excel</a></div></article>`).join("");
  }
  function socialReportTable(rows) {
    if(!rows.length)return `<div class="empty">No weekly report records match these filters.</div>`;
    return `<div class="table-wrap"><table><thead><tr><th>Platform / account</th><th>Reporting week</th><th>Audience</th><th>Net growth</th><th>Engagement</th><th>Status</th><th>Source / entered by</th><th>Details / evidence / actions</th></tr></thead><tbody>${rows.map(r=>{
      const editable=["Draft","Returned for Correction","Rejected"].includes(r.status);
      const metricRows=SOCIAL_METRICS.map(([key,label])=>`<tr><th>${esc(label)}</th><td>${socialValue(r.metrics[key])}</td></tr>`).join("");
      return `<tr><td>${esc(r.platform_name)}<br>${esc(r.account_handle)}</td><td>${esc(r.reporting_week)} – ${esc(r.reporting_week_end)}<br>Recorded ${esc(r.reporting_date)}</td>
        <td>${socialValue(r.metrics.audience_start)} → ${socialValue(r.metrics.audience_end)}</td><td>${socialValue(r.calculations.net_follower_growth)}<br>${socialPercent(r.calculations.audience_growth_percent)}</td>
        <td>${socialPercent(r.calculations.engagement_rate_percent)}<br><small>${esc(r.calculations.engagement_denominator)} denominator</small></td>
        <td><span class="badge">${esc(r.status)}</span>${r.review_comment?`<br><small>${esc(r.review_comment)}</small>`:""}</td>
        <td>${esc(r.source_label)}<br>${esc(r.entered_by)}<br>${esc(r.entered_at)}</td><td>
        <details><summary>View all metrics and report notes</summary><div class="table-wrap"><table><tbody>${metricRows}</tbody></table></div>
          <p><b>Best-performing content:</b> ${esc(r.best_content||"N/A")}</p><p><b>Comments/recommendations:</b> ${esc(r.recommendations||"N/A")}</p>
          <p><b>Engagement formula:</b> ${esc(r.calculations.engagement_formula)}</p><div class="row-actions">${r.evidence.map(e=>`<a class="button small" href="/api/social/evidence/${e.id}">${esc(e.name)} · ${e.size_bytes} bytes</a>`).join(" ")||"No evidence"}</div></details>
        ${editable?`<details><summary>Edit draft / correction</summary>${socialWeeklyForm(r.platform,r.account_id,r)}</details><button class="button small" data-social-action="submit-weekly" data-id="${r.id}">Submit for review</button>`:""}
        ${isRole("head_of_office")&&r.status==="Submitted"?`<div class="row-actions"><button class="button small primary" data-social-action="review-weekly" data-decision="approve" data-id="${r.id}">Approve</button><button class="button small" data-social-action="review-weekly" data-decision="correction" data-id="${r.id}">Request correction</button><button class="button small danger" data-social-action="review-weekly" data-decision="reject" data-id="${r.id}">Reject</button></div>`:""}</td></tr>`;
    }).join("")}</tbody></table></div>`;
  }
  async function refreshSocialWeekly() {
    const form=$("#social-weekly-filter"); if(!form)return;
    const params=new URLSearchParams(); for(const key of ["start","end","platform","account_id"])if(form.elements[key].value)params.set(key,form.elements[key].value);
    const rows=await api(`/api/social/weekly?${params}`); state.socialReports=rows;
    const target=$("#social-weekly-list"); if(!target)return;
    target.innerHTML=socialReportTable(rows);
  }
  function socialBarChart(rows,key,title,formatter=(v)=>String(v)) {return window.SocialCharts.renderBarChart(rows,key,title,formatter);}
  function socialTimeChart(series,key,title,formatter) {return socialBarChart(series,key,title,formatter);}
  async function refreshSocialAnalytics(start,end,platform,grain) {
    const target=$("#social-graphs");if(!target)return;
    try {
      const query=new URLSearchParams({start,end,grain});if(platform)query.set("platform",platform);
      const data=await api(`/api/social/analytics?${query}`);
      $("#social-engagement-method").textContent=data.formula;
      const timeGrowth=socialTimeChart(data.series,"net_follower_growth",`${grain[0].toUpperCase()+grain.slice(1)} audience growth`,v=>`${v>0?"+":""}${v}`);
      const comparisons=socialBarChart(data.platform_summary,"net_follower_growth","Platform comparison · net audience growth",v=>`${v>0?"+":""}${v}`);
      const engagement=socialTimeChart(data.series,"engagement_rate_percent","Engagement rate by selected period (%)",v=>`${v}%`);
      const reach=socialTimeChart(data.series,"reach","Reach by selected period");
      const impressions=socialTimeChart(data.series,"impressions","Impressions by selected period");
      const views=socialTimeChart(data.series,"views","Video views by selected period");
      const posts=socialTimeChart(data.series,"posts_published","Posts published by selected period");
      const videos=socialTimeChart(data.series,"videos_published","Videos published by selected period");
      const compared=data.series.filter(x=>x.previous_period);
      const previousTable=compared.length?`<details class="panel"><summary>Changes compared with the previous reported ${esc(grain)}</summary><div class="table-wrap"><table><thead><tr><th>Platform</th><th>Account</th><th>Current period</th><th>Previous period</th><th>Net growth change</th><th>Engagement change (pp)</th><th>Reach change</th><th>Impressions change</th><th>Views change</th><th>Posts / videos change</th></tr></thead><tbody>${compared.map(x=>`<tr><td>${esc(x.platform_name)}</td><td>${esc(x.account_handle||"N/A")}</td><td>${esc(x.period)}</td><td>${esc(x.previous_period)}</td><td>${socialValue(x.changes_vs_previous.net_follower_growth)}</td><td>${socialValue(x.changes_vs_previous.engagement_rate_percent)}</td><td>${socialValue(x.changes_vs_previous.reach)}</td><td>${socialValue(x.changes_vs_previous.impressions)}</td><td>${socialValue(x.changes_vs_previous.views)}</td><td>${socialValue(x.changes_vs_previous.posts_published)} / ${socialValue(x.changes_vs_previous.videos_published)}</td></tr>`).join("")}</tbody></table></div><p class="hint">Each change is current period minus the preceding period for the same platform. N/A remains unavailable.</p></details>`:`<p class="hint">No preceding period is available for comparisons in this selected range.</p>`;
      $("#social-graphs").innerHTML=`<p class="hint">${data.approved_weekly_report_count} approved weekly source report(s) in range.</p>${previousTable}<div class="social-chart-grid">${timeGrowth}${comparisons}${engagement}${reach}${impressions}${views}${posts}${videos}</div>`;
    }catch(e){target.innerHTML=`<div class="message error">${esc(e.message)}</div>`;}
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
  const eqOptions = (items, valueKey="id", labelKey="name") => items.map(x=>`<option value="${esc(x[valueKey])}">${esc(x[labelKey])}</option>`).join("");
  const eqDate = () => {const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;};
  const eqDateTime = () => {const d=new Date(Date.now()+2*60*60*1000);d.setMinutes(d.getMinutes()-d.getTimezoneOffset());return d.toISOString().slice(0,16);};
  async function loadEquipment() {
    const root=$("#view-equipment"); root.innerHTML=`<div class="page-heading"><div><h1>Equipment &amp; custody</h1><p>Live registered assets, shift custodians, authorizations, issues, returns and handovers.</p></div></div><p class="empty">Loading equipment records…</p>`;
    try {
      const [d,assets,issues,shifts,roster,handovers,auth] = await Promise.all([
        api("/api/equipment/dashboard"),api("/api/equipment/assets"),api("/api/equipment/requests"),
        api("/api/equipment/shifts"),api(`/api/equipment/custodians?shift_date=${eqDate()}`),
        api("/api/equipment/handovers"),api("/api/equipment/authorization-roles")]);
      state.equipmentAssets=assets; state.equipmentIssues=issues; state.equipmentShifts=shifts; state.equipmentRoster=roster;
      const cards=[["Current shift custodian",`${d.current_shift?.name||"—"}: ${(d.current_shift_custodians||[]).map(x=>x.name).join(", ")||"not assigned"}`],
        ["Previous shift custodian",`${d.previous_shift?.name||"—"}: ${(d.previous_shift_custodians||[]).map(x=>x.name).join(", ")||"not assigned"}`],
        ["Incoming shift custodian",`${d.incoming_shift?.name||"—"}: ${(d.incoming_shift_custodians||[]).map(x=>x.name).join(", ")||"not assigned"}`],
        ["Equipment in custody",d.equipment_in_custody],["Issued this shift",d.issued_during_current_shift],
        ["Returned this shift",d.returned_during_current_shift],["Outstanding",d.outstanding_equipment],
        ["Overdue",d.overdue_equipment],["Missing",d.missing_equipment],["Damaged / inspection",d.damaged_equipment],
        ["Pending authorization",d.pending_authorization]];
      const canManage=isRole("head_of_office","system_administrator");
      const assetForm=canManage?`<div class="panel"><h2>Register an individual physical asset</h2><p class="hint">After registration, use the Photo action to upload its required private PNG/JPEG photograph; assets without photos cannot be requested for issue.</p><form id="eq-asset-create" class="form-grid">
        <label>Unique asset number<input name="asset_tag" placeholder="CAM-001" required maxlength="50"></label><label>Category<input name="category" placeholder="Camera" required></label>
        <label>Equipment name<input name="name" placeholder="Camera body" required></label><label>Brand<input name="brand"></label>
        <label>Exact model<input name="model"></label><label>Serial number (optional)<input name="serial_number"></label>
        <label>Internal asset tag<input name="internal_tag"></label><label>Current location<input name="location" value="Equipment store"></label>
        <label>Condition<select name="condition"><option>New</option><option selected>Good</option><option>Fair</option><option>Poor</option></select></label>
        <label>Purchase date<input type="date" name="purchase_date"></label><label>Warranty until<input type="date" name="warranty_until"></label>
        <label>Department<select name="department_id"><option value="">None</option>${state.departments.map(x=>`<option value="${x.id}">${esc(x.name)}</option>`).join("")}</select></label>
        <label>Responsible user<select name="responsible_user_id"><option value="">None</option>${state.people.map(x=>`<option value="${x.id}">${esc(x.full_name)}</option>`).join("")}</select></label>
        <label class="wide">Notes<textarea name="notes"></textarea></label><div class="wide"><button class="button primary">Register asset</button></div></form></div>
        <div class="panel"><h2>Accessory relationship</h2><form id="eq-accessory-link" class="inline-form"><label>Main equipment<select name="parent_asset_id" required>${assets.map(a=>`<option value="${a.id}">${esc(a.asset_tag)} · ${esc(a.name)}</option>`).join("")}</select></label><label>Accessory<select name="accessory_asset_id" required>${assets.map(a=>`<option value="${a.id}">${esc(a.asset_tag)} · ${esc(a.name)}</option>`).join("")}</select></label><button class="button">Link individual accessory</button></form></div>`:"";
      const custodyPanel=canManage?`<div class="panel"><h2>Assign shift custodians</h2><form id="eq-custodian-assign" class="form-grid"><label>Shift<select name="shift_id">${eqOptions(shifts)}</select></label><label>Custodian<select name="custodian_id">${state.people.map(p=>`<option value="${p.id}">${esc(p.full_name)}</option>`).join("")}</select></label><label>Effective from<input type="date" name="effective_from" value="${eqDate()}" required></label><label>Effective to (optional)<input type="date" name="effective_to"></label><label class="wide">Assignment note<input name="reason"></label><div class="wide"><button class="button">Record custodian assignment</button></div></form>
        <h3>Replacement for absence</h3><form id="eq-custodian-replace" class="form-grid"><label>Shift<select name="shift_id">${eqOptions(shifts)}</select></label><label>Date<input type="date" name="shift_date" value="${eqDate()}" required></label><label>Original custodian<select name="original_custodian_id">${state.people.map(p=>`<option value="${p.id}">${esc(p.full_name)}</option>`).join("")}</select></label><label>Replacement<select name="replacement_custodian_id">${state.people.map(p=>`<option value="${p.id}">${esc(p.full_name)}</option>`).join("")}</select></label><label class="wide">Reason (required)<input name="reason" required minlength="3"></label><div class="wide"><button class="button">Record replacement</button></div></form>
        ${isRole("head_of_office")?`<h3>Authorization roles</h3><form id="eq-auth-roles" class="inline-form"><label>Roles permitted to authorize <select name="roles" multiple size="4">${(await api("/api/roles")).map(r=>`<option value="${esc(r.id)}" ${auth.roles.includes(r.id)?"selected":""}>${esc(r.name)}</option>`).join("")}</select></label><button class="button">Save authorization policy</button><span class="hint">The Head of Office configures policy; an empty policy blocks all issue authorization.</span></form>`:""}</div>`:"";
      const issueForm=`<div class="panel"><h2>Request equipment</h2><form id="eq-request-create" class="form-grid"><label>Individual device / accessory<select name="asset_ids" multiple size="5" required>${assets.map(a=>`<option value="${a.id}" ${a.availability!=="Available"||!a.has_photo?"disabled":""}>${esc(a.asset_tag)} · ${esc(a.name)} · ${esc(a.availability)}${!a.has_photo?" · photo required":""}</option>`).join("")}</select><span class="hint">Select main devices; linked accessories are added automatically. Each physical item stays separately tracked.</span></label><label>Borrower name<input name="borrower_name" value="${esc(state.user.full_name)}" required></label><label>Borrower's office<input name="borrower_office" value="Office" required></label><label>Shift for issue<select name="shift_id">${eqOptions(shifts)}</select></label><label>Issue date<input type="date" name="shift_date" value="${eqDate()}" required></label><label>Expected return<input type="datetime-local" name="expected_return_at" value="${eqDateTime()}" required></label><label class="wide">Purpose<textarea name="purpose"></textarea></label><label><input type="checkbox" name="external" value="true"> External office borrower (Head/Editor only)</label><div class="wide"><button class="button primary">Submit request for authorization</button></div></form></div>`;
      const assetsTable=assets.length?`<div class="table-wrap"><table><thead><tr><th>Asset</th><th>Photo / QR</th><th>Category, brand &amp; model</th><th>Serial / internal tag</th><th>Condition / availability</th><th>Location / responsible</th><th>Accessories</th><th>Actions</th></tr></thead><tbody>${assets.map(a=>`<tr><td><b>${esc(a.asset_tag)}</b><br>${esc(a.name)}</td><td>${a.has_photo?`<img alt="Asset photo" width="52" src="/api/equipment/assets/${a.id}/photo">`:"—"}<br><a href="/api/equipment/assets/${a.id}/qr.svg" target="_blank" rel="noopener">QR label</a></td><td>${esc(a.category)} · ${esc(a.brand)} ${esc(a.model)}</td><td>${esc(a.serial_number||"not recorded")} / ${esc(a.internal_tag||"—")}</td><td>${esc(a.condition)} / ${esc(a.availability)}</td><td>${esc(a.location)} · ${esc(a.responsible_user||a.department||"—")}</td><td>${a.accessories.map(x=>esc(x.asset_tag)+" · "+esc(x.name)).join("<br>")||"—"}</td><td>${canManage?`<button class="button small" data-eq-action="history" data-id="${a.id}">History</button><button class="button small" data-eq-action="edit-asset" data-id="${a.id}">Edit</button><button class="button small" data-eq-action="photo" data-id="${a.id}">Photo</button>${a.availability==="Damaged"?`<button class="button small" data-eq-action="inspect" data-id="${a.id}">Inspect</button>`:""}`:"—"}</td></tr>`).join("")}</tbody></table></div>`:`<div class="empty">No equipment assets registered. Register each physical device separately.</div>`;
      const requestRows=issues.length ? issues.map(i=>{
        const authorized=i.authorized_by?`by ${esc(i.authorized_by)} (${esc(i.authorized_role_id)}) at ${esc(i.authorized_at)}`:"pending";
        const issued=i.issued_by?`${esc(i.issued_by)} at ${esc(i.issued_at)}`:"not issued";
        const itemRows=i.items.map(x=>`<tr><td>${esc(x.asset_tag)} · ${esc(x.name)}</td><td>${esc(x.condition_before||"—")}</td><td>${esc(x.return_condition||"outstanding")}${x.returned_at ? " · "+esc(x.returned_at) : ""}</td><td>${esc(state.people.find(p=>p.id===x.received_by_id)?.full_name||"—")}</td><td>${x.missing_reported?"Reported missing":"—"}</td></tr>`).join("");
        const actions=`${i.status==="Pending authorization"&&isRole("head_of_office","editor")?`<button class="button small" data-eq-action="authorize" data-id="${i.id}">Authorize</button>`:""}${i.status==="Authorized"?`<button class="button small primary" data-eq-action="issue" data-id="${i.id}">Record physical issue</button>`:""}${["Issued","Partially returned"].includes(i.status)&&!i.borrower_acknowledged_at?`<button class="button small" data-eq-action="borrower-ack" data-id="${i.id}" data-external="${i.external}">Acknowledge receipt</button>`:""}${["Issued","Partially returned"].includes(i.status)?`<button class="button small" data-eq-action="return" data-id="${i.id}">Record return / missing</button>`:""}`;
        return `<article class="task-card"><div class="panel-head"><h3>Request #${i.id} · ${esc(i.borrower_name)} · ${esc(i.borrower_office)}</h3><span class="badge">${esc(i.status)}</span></div><p>Authorization: ${esc(i.authorization_method||"pending")} ${authorized}<br>Issued by custodian: ${issued} · Expected back ${esc(i.expected_return_at)} · Outstanding ${i.outstanding_count}</p><div class="table-wrap"><table><thead><tr><th>Asset</th><th>Before</th><th>Return condition/time</th><th>Received by</th><th>Missing</th></tr></thead><tbody>${itemRows}</tbody></table></div><div class="row-actions">${actions}</div></article>`;
      }).join("") : `<div class="empty">No equipment requests yet.</div>`;
      const handoverForm=`<div class="panel"><h2>Custody shift handover</h2><form id="eq-handover-create" class="form-grid"><label>Outgoing shift<select name="outgoing_shift_id">${eqOptions(shifts)}</select></label><label>Incoming shift<select name="incoming_shift_id">${eqOptions(shifts)}</select></label><label>Outgoing custodian<select name="outgoing_custodian_id">${state.people.map(p=>`<option value="${p.id}">${esc(p.full_name)}</option>`).join("")}</select></label><label>Incoming custodian<select name="incoming_custodian_id">${state.people.map(p=>`<option value="${p.id}">${esc(p.full_name)}</option>`).join("")}</select></label><label>Date<input type="date" name="shift_date" value="${eqDate()}" required></label><label class="wide">Discrepancies / handover notes<textarea name="discrepancies"></textarea></label><div class="wide"><button class="button">Create handover snapshot</button></div></form><p class="hint">Handover snapshots every outstanding item and never marks anything returned.</p><div id="eq-handovers">${handovers.map(h=>`<article class="task-card"><b>Handover #${h.id}</b> · ${esc(h.outgoing_custodian)} (${esc(h.outgoing_shift)}) → ${esc(h.incoming_custodian)} (${esc(h.incoming_shift)}) · ${esc(h.shift_date)}<p>Outstanding snapshot: ${h.outstanding_items.map(x=>`${esc(x.asset_tag)} → ${esc(x.borrower_name)} (${esc(x.borrower_office)}), due ${esc(x.expected_return_at)}`).join("; ")||"none"}<br>Outgoing acknowledgement: ${esc(h.outgoing_ack_at||"pending")} · incoming: ${esc(h.incoming_ack_at||"pending")}<br>Discrepancies: ${esc(h.discrepancies||"none")}</p><div class="row-actions">${h.outgoing_custodian_id===state.user.id&&!h.outgoing_ack_at?`<button class="button small" data-eq-action="handover-ack" data-id="${h.id}">Outgoing acknowledges</button>`:""}${h.incoming_custodian_id===state.user.id&&!h.incoming_ack_at?`<button class="button small" data-eq-action="handover-ack" data-id="${h.id}">Incoming acknowledges</button>`:""}${isRole("head_of_office")&&!h.reviewed_at&&h.outgoing_ack_at&&h.incoming_ack_at?`<button class="button small" data-eq-action="handover-review" data-id="${h.id}">Head review</button>`:""}</div></article>`).join("")||"<p class=\"hint\">No handovers recorded.</p>"}</div></div>`;
      const reportPanel=isRole("head_of_office","system_administrator")?`<div class="panel"><h2>Equipment reports &amp; complete asset history</h2><div class="inline-form"><label>Report<select id="eq-report-name"><option value="custodians">Shift custodian accountability</option><option value="issued-by-custodian">Issued by custodian</option><option value="received-by-custodian">Received by custodian</option><option value="currently-borrowed">Currently borrowed</option><option value="external-borrowing">External office borrowing</option><option value="overdue">Overdue by borrower</option><option value="missing">Missing equipment</option><option value="damaged">Damaged / awaiting inspection</option><option value="handovers">Shift handovers</option></select></label><button class="button" data-eq-action="report">Load report</button></div><pre id="eq-report-output" class="hint"></pre></div>`:"";
      root.innerHTML=`<div class="page-heading"><div><h1>Equipment &amp; shift custody</h1><p>Inventory and accountability from the live application database · ${esc(d.date)}</p></div></div><div class="grid">${cards.map(([n,v])=>`<div class="card stat"><div class="label">${esc(n)}</div><div class="value" style="font-size:1.05rem">${esc(v)}</div></div>`).join("")}</div>${assetForm}${custodyPanel}<div class="panel"><h2>Individual asset register</h2>${assetsTable}</div>${issueForm}<div class="panel"><h2>Requests and current loans</h2>${requestRows}</div>${handoverForm}${reportPanel}`;
    } catch(e) { root.innerHTML=`<div class="message error">${esc(e.message)}</div>`; }
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
    const loaders={dashboard:loadDashboard,tasks:loadTasks,timetable:loadTimetable,reports:loadReports,analytics:loadAnalytics,equipment:loadEquipment,social:loadSocial,accounts:loadAccounts,audit:loadAudit};
    if (loaders[name]) await loaders[name]();
  }
  function socialBody(form, platform) {
    const fd=new FormData(form),metrics={};
    for(const [key] of SOCIAL_METRICS){const raw=String(fd.get(key)||"").trim();if(raw===""||raw.toUpperCase()==="N/A")metrics[key]=null;else if(/^\d+$/.test(raw))metrics[key]=Number(raw);else throw new Error(`${key.replaceAll("_"," ")} must be a whole number or N/A`);}
    return {platform,account_id:Number(form.dataset.account),reporting_date:fd.get("reporting_date"),reporting_week:fd.get("reporting_week"),metrics,
      best_content:fd.get("best_content")||"",recommendations:fd.get("recommendations")||""};
  }
  async function uploadSocialEvidence(form, reportId) {
    const files=form.elements.evidence?.files||[];if(!files.length)return;
    const fd=new FormData();for(const f of files)fd.append("files",f);
    await api(`/api/social/weekly/${reportId}/evidence`,{method:"POST",body:fd});
  }
  async function loadSubmissions(taskId) {
    const target=$(`#submissions-${taskId}`); if(!target) return;
    try {const rows=await api(`/api/tasks/${taskId}/submissions`); target.innerHTML=rows.length?rows.map(s=>`<div class="panel"><h3>Submission · ${esc(s.created_at.replace("T"," "))}</h3><p>${esc(s.report)}</p>${s.notes?`<p class="hint">${esc(s.notes)}</p>`:""}<div class="row-actions">${s.attachments.map(a=>`<a class="button small" href="/api/attachments/${a.id}">${esc(a.name)}</a>`).join("")}</div>${isRole("head_of_office","editor") && s.reviewable?`<div class="row-actions"><button class="button small primary" data-action="verify" data-id="${s.id}" data-decision="approve">Verify</button><button class="button small" data-action="verify" data-id="${s.id}" data-decision="request_correction">Request correction</button><button class="button small danger" data-action="verify" data-id="${s.id}" data-decision="reject">Reject</button></div>`:""}</div>`).join(""):`<p class="hint">No submissions yet.</p>`;}
    catch(e){target.innerHTML=`<div class="message error">${esc(e.message)}</div>`;}
  }
  document.addEventListener("submit", async event=>{
    const form=event.target;
    if(!form.id?.startsWith("social-"))return;
    event.preventDefault(); const fd=new FormData(form);
    try {
      if(form.id.startsWith("social-create-")||form.id.startsWith("social-edit-")){
        const reportId=form.dataset.report, body=socialBody(form,form.dataset.platform);
        const result=reportId?await api(`/api/social/weekly/${reportId}`,{method:"PUT",body}):await api("/api/social/weekly",{method:"POST",body});
        await uploadSocialEvidence(form,result.id);
        message(reportId?"Corrected draft saved; resubmit it for review.":"Manual weekly draft saved. Add evidence before submitting.","success");
        await loadSocial();return;
      }
      if(form.id.startsWith("social-account-create-")||form.id.startsWith("social-account-edit-")){
        const editing=form.id.startsWith("social-account-edit-"), accountBody={account_name:fd.get("account_name"),account_handle:fd.get("account_handle"),profile_url:fd.get("profile_url")||null};
        if(editing) await api(`/api/social/accounts/${form.id.replace("social-account-edit-","")}`,{method:"PUT",body:accountBody});
        else await api("/api/social/accounts",{method:"POST",body:{...accountBody,platform:form.dataset.platform}});
        message(editing?"Verified social account updated.":"Verified social account registered.","success");await loadSocial();return;
      }
      if(form.id==="social-officers"){
        const user_ids=$$("input[name=user_ids]:checked",form).map(x=>Number(x.value));
        await api("/api/social/officers",{method:"PUT",body:{user_ids}});message("Designated reporting officers saved.","success");await loadSocial();return;
      }
      if(form.id==="social-weekly-filter"){await refreshSocialWeekly();return;}
      if(form.id==="social-analytics-filter"){
        await refreshSocialAnalytics(fd.get("start"),fd.get("end"),fd.get("platform"),fd.get("grain"));return;
      }
      if(form.id==="social-quarter-generate"){
        await api("/api/social/quarters/generate",{method:"POST",body:{year:Number(fd.get("year")),quarter:Number(fd.get("quarter"))}});
        message("Quarterly report generated from approved weekly records.","success");await loadSocial();return;
      }
      if(form.id.startsWith("social-quarter-edit-")){
        const id=form.id.replace("social-quarter-edit-","");
        await api(`/api/social/quarters/${id}`,{method:"PUT",body:{management_notes:fd.get("management_notes")}});
        message("Quarterly management notes saved.","success");await loadSocial();return;
      }
      if(form.id==="social-import"){
        const file=form.elements.file.files[0];if(!file)throw new Error("Choose a CSV or XLSX file first");
        state.socialPreviewFile=file;
        const body=new FormData();body.append("file",file);
        const preview=await api("/api/social/imports/preview",{method:"POST",body});
        const errors=preview.errors.map(x=>`<li>Row ${x.row_number}: ${esc(x.error)}</li>`).join("");
        const previewHead=SOCIAL_METRICS.map(([key,label])=>`<th>${esc(label)}</th>`).join("");
        const ready=preview.rows.map(x=>`<tr><td>${x.row_number}</td><td>${esc(x.platform)}</td><td>${esc(x.account_handle||"N/A")}</td><td>${esc(x.reporting_date)}</td><td>${esc(x.reporting_week)}</td>${SOCIAL_METRICS.map(([key])=>`<td>${socialValue(x.metrics[key])}</td>`).join("")}<td>${esc(x.best_content||"N/A")}</td><td>${esc(x.recommendations||"N/A")}</td></tr>`).join("");
        $("#social-import-preview").innerHTML=`<div class="message ${preview.can_commit?"success":"error"}" role="status">${preview.total_rows} row(s): ${preview.ready_count} ready; ${preview.error_count} error(s). ${preview.can_commit?"Review then import. No data is saved until you confirm import.":"Correct the listed rows/duplicate periods in the file and preview again."}</div>${ready?`<div class="table-wrap"><table><thead><tr><th>Row</th><th>Platform</th><th>Account</th><th>Reporting date</th><th>Week</th>${previewHead}<th>Best content</th><th>Recommendations</th></tr></thead><tbody>${ready}</tbody></table></div>`:""}${errors?`<ul>${errors}</ul>`:""}${preview.can_commit?`<form id="social-import-commit"><p>Original file will be retained as evidence for each imported draft; source is labeled Imported from file.</p><button class="button primary">Confirm import ${preview.ready_count} row(s)</button></form>`:""}`;
        return;
      }
      if(form.id==="social-import-commit"){
        if(!state.socialPreviewFile)throw new Error("Select and preview the import file again");
        const body=new FormData();body.append("file",state.socialPreviewFile);
        const result=await api("/api/social/imports/commit",{method:"POST",body});
        state.socialPreviewFile=null;message(`${result.created_count} imported draft report(s) saved with file evidence.`,"success");await loadSocial();return;
      }
    }catch(e){message(e.message,"error");}
  });
  document.addEventListener("click", async event=>{
    const social=event.target.closest("[data-social-action]");
    if(social){
      const {socialAction,id,decision}=social.dataset;
      try{
        if(socialAction==="submit-weekly")await api(`/api/social/weekly/${id}/submit`,{method:"POST"});
        else if(socialAction==="review-weekly"||socialAction==="review-quarter"){
          let comment=prompt(decision==="approve"?"Optional approval comment:":"Enter the reason or correction request:","");
          if(comment===null)return;if(decision!=="approve"&&comment.trim().length<3)throw new Error("Enter a review reason of at least 3 characters");
          const path=socialAction==="review-weekly"?`/api/social/weekly/${id}/review`:`/api/social/quarters/${id}/review`;
          await api(path,{method:"POST",body:{decision,comment}});
        }else if(socialAction==="submit-quarter")await api(`/api/social/quarters/${id}/submit`,{method:"POST"});
        message("Social media workflow action saved.","success");await loadSocial();
      }catch(e){message(e.message,"error");}
      return;
    }
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
  document.addEventListener("click", async event=>{
    const b=event.target.closest("[data-eq-action]"); if(!b)return;
    const id=Number(b.dataset.id);
    try {
      if(b.dataset.eqAction==="authorize") {
        const method=prompt("Authorization method: Head of Office authorization, Editor authorization, or Other delegated authorization","Head of Office authorization"); if(!method)return;
        const remarks=prompt("Authorization remarks (required; include delegation details if applicable):"); if(!remarks||remarks.trim().length<3)return;
        await api(`/api/equipment/requests/${id}/authorize`,{method:"POST",body:{method,remarks}});
      } else if(b.dataset.eqAction==="issue") {
        const req=state.equipmentIssues.find(x=>x.id===id); if(!req)return;
        const conditions={}; for(const item of req.items){const value=prompt(`Physical condition before issue for ${item.asset_tag} (${item.name})`,"Good");if(!value)return;conditions[item.asset_id]=value;}
        await api(`/api/equipment/requests/${id}/issue`,{method:"POST",body:{conditions}});
      } else if(b.dataset.eqAction==="borrower-ack") {
        let body={acknowledged:true}; if(b.dataset.external==="true"){const name=prompt("Confirm the external borrower’s full name as shown on the request:");if(!name)return;body.borrower_name=name;}
        await api(`/api/equipment/requests/${id}/acknowledge`,{method:"POST",body});
      } else if(b.dataset.eqAction==="return") {
        const req=state.equipmentIssues.find(x=>x.id===id); if(!req)return;
        const outstanding=req.items.filter(x=>!x.returned_at);
        const valid=outstanding.map(x=>`${x.asset_id}=${x.asset_tag}`).join(", ");
        const returnedText=prompt(`Enter asset IDs physically received, comma separated. Outstanding: ${valid}. Leave blank if none.`,""); if(returnedText===null)return;
        const missingText=prompt("Enter outstanding asset IDs reported missing, comma separated (do not list physically returned items):",""); if(missingText===null)return;
        const returned=returnedText.split(",").map(x=>x.trim()).filter(Boolean).map(raw=>{const assetId=Number(raw);const item=outstanding.find(x=>x.asset_id===assetId);if(!item)throw new Error(`Asset ${raw} is not outstanding on this request`);const condition=prompt(`Condition after return for ${item.asset_tag}: New, Good, Fair, Poor or Damaged`,"Good");if(!condition)throw new Error("Return condition is required");const damage_notes=prompt(`Damage report for ${item.asset_tag} (leave blank if none):`,"")||"";return {asset_id:assetId,condition,damage_notes};});
        const missing_asset_ids=missingText.split(",").map(x=>x.trim()).filter(Boolean).map(Number);
        const shiftId=Number(prompt(`Receiving custodian’s shift ID (${state.equipmentShifts.map(s=>`${s.id} ${s.name}`).join("; ")})`,String(req.shift_id))); if(!shiftId)return;
        const shiftDate=prompt("Actual date received/reported (YYYY-MM-DD):",today());if(!shiftDate)return;
        const notes=prompt("Return / discrepancy notes:","")||"";
        await api(`/api/equipment/requests/${id}/return`,{method:"POST",body:{shift_id:shiftId,shift_date:shiftDate,returned,missing_asset_ids,notes}});
      } else if(b.dataset.eqAction==="history") {
        const data=await api(`/api/equipment/reports/assets/${id}/history`); const pre=$("#eq-report-output"); if(pre)pre.textContent=JSON.stringify(data,null,2); message("Asset history loaded in the report panel.","success"); return;
      } else if(b.dataset.eqAction==="report") {
        const name=$("#eq-report-name")?.value; const data=await api(`/api/equipment/reports/${name}`); $("#eq-report-output").textContent=JSON.stringify(data,null,2); return;
      } else if(b.dataset.eqAction==="handover-ack") {
        const discrepancies=prompt("Handover discrepancy or acknowledgement note (optional):","")||"";
        await api(`/api/equipment/handovers/${id}/acknowledge`,{method:"POST",body:{discrepancies}});
      } else if(b.dataset.eqAction==="handover-review") {
        const comment=prompt("Head of Office review comment:","")||"";
        await api(`/api/equipment/handovers/${id}/review`,{method:"POST",body:{comment}});
      } else if(b.dataset.eqAction==="edit-asset") {
        const asset=state.equipmentAssets.find(x=>x.id===id); if(!asset)return;
        const category=prompt("Category:",asset.category);if(category===null)return;
        const name=prompt("Equipment name:",asset.name);if(name===null)return;
        const model=prompt("Exact model:",asset.model);if(model===null)return;
        const serial_number=prompt("Manufacturer serial number (leave blank if unknown):",asset.serial_number||"");if(serial_number===null)return;
        const location=prompt("Current location:",asset.location);if(location===null)return;
        const condition=prompt("Condition (New, Good, Fair, Poor, Damaged):",asset.condition);if(condition===null)return;
        const responsible=prompt(`Responsible user ID, or blank for none (${state.people.map(p=>`${p.id}=${p.full_name}`).join("; ")})`,asset.responsible_user_id||"");if(responsible===null)return;
        const notes=prompt("Notes:",asset.notes||"");if(notes===null)return;
        await api(`/api/equipment/assets/${id}`,{method:"PATCH",body:{category,name,model,serial_number,location,condition,responsible_user_id:responsible?Number(responsible):null,notes}});
      } else if(b.dataset.eqAction==="inspect") {
        const condition=prompt("Inspection condition (New, Good, Fair, Poor, Damaged):","Good");if(!condition)return;
        const disposition=prompt("Disposition after inspection (Available, Maintenance, Damaged, Retired):","Available");if(!disposition)return;
        const notes=prompt("Inspection findings (required):");if(!notes)return;
        await api(`/api/equipment/assets/${id}/inspect`,{method:"POST",body:{condition,disposition,notes}});
      } else if(b.dataset.eqAction==="photo") {
        const input=document.createElement("input");input.type="file";input.accept="image/png,image/jpeg";
        await new Promise(resolve=>{input.onchange=async()=>{if(!input.files[0])return resolve();const fd=new FormData();fd.append("file",input.files[0]);try{await api(`/api/equipment/assets/${id}/photo`,{method:"POST",body:fd});resolve();}catch(e){message(e.message,"error");resolve();}};input.click();});
      }
      message("Equipment action recorded.","success"); await loadEquipment();
    } catch(e){message(e.message,"error");}
  });
  document.addEventListener("submit", async event=>{
    const form=event.target; if(!form.id?.startsWith("eq-"))return; event.preventDefault(); const fd=new FormData(form);
    try {
      if(form.id==="eq-asset-create") {
        const body={asset_tag:fd.get("asset_tag"),category:fd.get("category"),name:fd.get("name"),brand:fd.get("brand"),model:fd.get("model"),serial_number:fd.get("serial_number")||null,internal_tag:fd.get("internal_tag"),location:fd.get("location"),condition:fd.get("condition"),purchase_date:fd.get("purchase_date")||null,warranty_until:fd.get("warranty_until")||null,department_id:fd.get("department_id")?Number(fd.get("department_id")):null,responsible_user_id:fd.get("responsible_user_id")?Number(fd.get("responsible_user_id")):null,notes:fd.get("notes")};
        await api("/api/equipment/assets",{method:"POST",body});
      } else if(form.id==="eq-accessory-link") {
        await api(`/api/equipment/assets/${fd.get("parent_asset_id")}/accessories`,{method:"POST",body:{accessory_asset_id:Number(fd.get("accessory_asset_id"))}});
      } else if(form.id==="eq-custodian-assign") {
        await api("/api/equipment/custodians",{method:"POST",body:{shift_id:Number(fd.get("shift_id")),custodian_id:Number(fd.get("custodian_id")),effective_from:fd.get("effective_from"),effective_to:fd.get("effective_to")||null,reason:fd.get("reason")}});
      } else if(form.id==="eq-custodian-replace") {
        await api("/api/equipment/custodians/replacements",{method:"POST",body:{shift_id:Number(fd.get("shift_id")),shift_date:fd.get("shift_date"),original_custodian_id:Number(fd.get("original_custodian_id")),replacement_custodian_id:Number(fd.get("replacement_custodian_id")),reason:fd.get("reason")}});
      } else if(form.id==="eq-auth-roles") {
        await api("/api/equipment/authorization-roles",{method:"PUT",body:{roles:$$('select[name="roles"] option:checked',form).map(o=>o.value)}});
      } else if(form.id==="eq-request-create") {
        const external=fd.get("external")==="true";const body={asset_ids:$$('select[name="asset_ids"] option:checked',form).map(o=>Number(o.value)),borrower_name:fd.get("borrower_name"),borrower_office:fd.get("borrower_office"),external,shift_id:Number(fd.get("shift_id")),shift_date:fd.get("shift_date"),expected_return_at:new Date(fd.get("expected_return_at")).toISOString(),purpose:fd.get("purpose")};
        await api("/api/equipment/requests",{method:"POST",body});
      } else if(form.id==="eq-handover-create") {
        await api("/api/equipment/handovers",{method:"POST",body:{outgoing_shift_id:Number(fd.get("outgoing_shift_id")),incoming_shift_id:Number(fd.get("incoming_shift_id")),shift_date:fd.get("shift_date"),outgoing_custodian_id:Number(fd.get("outgoing_custodian_id")),incoming_custodian_id:Number(fd.get("incoming_custodian_id")),discrepancies:fd.get("discrepancies")}});
      }
      message("Equipment record saved.","success"); await loadEquipment();
    } catch(e){message(e.message,"error");}
  });

  $("#password-button").addEventListener("click",async()=>{const current_password=prompt("Current password:");if(!current_password)return;const new_password=prompt("New password (at least 12 characters):");if(!new_password)return;try{await api("/api/auth/change-password",{method:"POST",body:new URLSearchParams({current_password,new_password})});message("Password changed. Sign in again.","success");showLogin();}catch(e){message(e.message,"error");}});
  $("#logout-button").addEventListener("click",async()=>{try{await api("/api/auth/logout",{method:"POST"});}catch(_){}showLogin();});
  api("/api/auth/me").then(startSession).catch(()=>showLogin());
})();
