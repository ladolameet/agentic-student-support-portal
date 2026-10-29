const $ = (id) => document.getElementById(id);
const icon = (n) => `<svg class="ic"><use href="#i-${n}"/></svg>`;

// Curated Demo Questions categorized for high-impact student assistance
const QUICK = [
  { cat: "finance", tag: "Fee Record", icon: "wallet", title: "Check My Fee Balance", desc: "Current balance, payments received, and semester deadlines.", q: "What is my fee balance?" },
  { cat: "finance", tag: "Late Policy", icon: "calendar", title: "Late Payment Penalties", desc: "Weekly penalty charges, deregistration rules, and grace periods.", q: "What is the late fee if I pay after the due date?" },
  { cat: "scholarship", tag: "Scholarship", icon: "award", title: "My Scholarship Status", desc: "Application review stage, awarded concessions, and committee notes.", q: "What is my scholarship status?" },
  { cat: "scholarship", tag: "Merit Policy", icon: "book", title: "Merit Scholarship Criteria", desc: "CGPA cutoffs, percentage tuition waivers, and renewal terms.", q: "What are the Merit scholarship criteria?" },
  { cat: "support", tag: "Payment Issue", icon: "alert", title: "Payment Portal Crash", desc: "Double debit reconciliation, reporting window, and refund SLA.", q: "The payment portal failed. What should I do?" },
  { cat: "support", tag: "Help Desk", icon: "ticket", title: "Create Support Ticket", desc: "Open an official student grievance ticket with tracking ID.", q: "Please create a support ticket: my payment portal crashed while paying." },
  { cat: "academics", tag: "Attendance", icon: "check", title: "75% Attendance Requirement", desc: "Minimum threshold, medical condonation, and exam detention rules.", q: "What is the minimum attendance requirement?" },
  { cat: "academics", tag: "Academics", icon: "book", title: "Course Change Procedure", desc: "Add/drop transfer window, prerequisites, and approval procedure.", q: "Who has to approve a course change request?" },
  { cat: "privacy", tag: "Verification", icon: "shield", title: "Update Registered Email", desc: "Verified record update with confirmation card before saving.", q: "I want to update my registered email to meet.patel.new@example.com" },
  { cat: "privacy", tag: "Memory", icon: "user", title: "Remember Programme & Room", desc: "Store personal student details for future personalized answers.", q: "I am studying in PGDM Agentic AI and I stay in Hostel Block B Room 204." },
  { cat: "privacy", tag: "Recall", icon: "sparkles", title: "Recall From Memory", desc: "Test the assistant recalling remembered hostel & programme details.", q: "What programme am I studying and which hostel room do I stay in based on my saved memory?" },
  { cat: "academics", tag: "Calendar", icon: "calendar", title: "Working Days Definition", desc: "Official calendar rules, weekend exclusions, and office hours.", q: "What counts as a working day?" },
  { cat: "support", tag: "Escalation", icon: "alert", title: "Escalation Process", desc: "Escalation contacts for unresolved student tickets.", q: "My ticket was not answered, who do I escalate to?" }
];

const TOOL_LABEL = {
  get_fee_status: ["wallet", "Fee Record"], check_scholarship_status: ["award", "Scholarship Record"],
  create_support_ticket: ["ticket", "Support Ticket"], search_policy: ["book", "Policy Handbook"],
  save_memory: ["user", "Memory Saved"], get_saved_memory: ["user", "Memory Recalled"],
  request_record_change: ["shield", "Verification Card"], check_request_status: ["shield", "Verification Status"],
};

let history = [];
let sessionId = Math.random().toString(36).slice(2, 10);
let me = { id: "", name: "" };

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clock = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const initials = (n) => (n || "?").replace(/\(.*?\)/g, "").trim().split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
const scrollDown = () => { $("chat").scrollTop = $("chat").scrollHeight; };

// Rich Markdown formatter: parses markdown tables, headers, lists, and bold text via marked.js
function format(text) {
  const m = window.marked || (typeof marked !== "undefined" ? marked : null);
  if (m && typeof m.parse === "function") {
    try {
      return m.parse(text, { breaks: true, gfm: true });
    } catch (e) {
      console.error("Markdown parse error:", e);
    }
  }
  const inline = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  return text.trim().split(/\n{2,}/).map((block) => {
    const lines = block.split("\n");
    if (lines.every((l) => /^\s*[-*] /.test(l))) return "<ul>" + lines.map((l) => `<li>${inline(l.replace(/^\s*[-*] /, ""))}</li>`).join("") + "</ul>";
    return "<p>" + lines.map(inline).join("<br>") + "</p>";
  }).join("");
}

function clearWelcome() { 
  const w = $("chat").querySelector(".welcome-container"); 
  if (w) w.remove(); 
}

function userMsg(text) {
  clearWelcome();
  const r = document.createElement("div");
  r.className = "row user";
  r.innerHTML = `<div class="col"><div class="bubble"></div><div class="time">${clock()}</div></div>`;
  r.querySelector(".bubble").textContent = text;
  $("chat").appendChild(r);
  scrollDown();
}

function botMsg(text, result, isError) {
  const r = document.createElement("div");
  r.className = "row bot" + (isError ? " err" : "");
  let extra = "";
  if (result) {
    // Clean citation sources bar (deduplicated)
    const sourceTitles = [];
    (result.chunks || []).forEach((c) => {
      if (c.title && !sourceTitles.includes(c.title)) sourceTitles.push(c.title);
    });
    if (sourceTitles.length) {
      extra += `<div class="sources-bar"><svg class="ic sm"><use href="#i-book"/></svg><span>Sources:</span> ${sourceTitles.map(t => `<span class="source-tag">${esc(t)}</span>`).join("")}</div>`;
    }

    const ticket = /TCK-[0-9A-F]{8}/.exec(text);
    if (ticket && result.tools_called.some((t) => t.name === "create_support_ticket" && t.ok)) {
      extra += `<div class="ticket">${icon("ticket")}<div><small>Official Support Ticket Generated</small><b>${ticket[0]}</b><small>Standard support turnaround: 2 working days.</small></div></div>`;
    }
    const apr = /APR-[0-9A-F]{8}/.exec(text);
    if (apr && result.tools_called.some((t) => t.name === "request_record_change" && t.ok)) {
      extra += `<div class="ticket approval confirm" data-apr="${apr[0]}">${icon("alert")}<div><small>Loading approval card...</small></div></div>`;
    }
    if (result.audit && result.audit.some((a) => a.decision === "denied")) {
      extra += `<div class="ticket blocked">${icon("alert")}<div><small>Authorization Refusal</small><span>Access restricted strictly to the signed-in student's records.</span></div></div>`;
    }

    // Suggested follow-up prompt chips (clean and compact)
    if (result.suggested_questions && result.suggested_questions.length) {
      extra += `<div class="followup-chips">
        ${result.suggested_questions.map((q) => `<button type="button" class="chip-btn" data-q="${esc(q)}">${esc(q)}</button>`).join("")}
      </div>`;
    }
  }
  r.innerHTML = `<div class="who">${icon("bot")}</div><div class="col"><div class="bubble">${format(text)}</div>${extra}<div class="time">Student Assistant • ${clock()}</div></div>`;
  $("chat").appendChild(r);
  r.querySelectorAll(".confirm").forEach(hydrateConfirm);
  r.querySelectorAll(".chip-btn").forEach((btn) => {
    btn.onclick = () => send(btn.dataset.q);
  });
  scrollDown();
}

// In-chat confirmation of sensitive record actions
async function hydrateConfirm(card) {
  const items = await (await fetch("/api/requests")).json();
  renderConfirm(card, items.find((x) => x.approval_id === card.dataset.apr));
}

function renderConfirm(card, x) {
  if (!x) { card.innerHTML = `${icon("alert")}<div><small>Request not found</small></div>`; return; }
  const what = x.field === "email" ? "registered email address" : "registered phone number";
  let body;
  if (x.status === "pending" && !x.expired) {
    body = `<small>Security Verification Required</small><b>${esc(x.approval_id)}</b>
      <div>Change your ${what} from <s>${esc(x.old_value)}</s> to <strong>${esc(x.new_value)}</strong></div>
      <div class="confirm-actions">
        <button class="btn btn-sm btn-primary" data-d="approve">Confirm & Update</button>
        <button class="btn btn-sm btn-outline-secondary" data-d="reject">Cancel</button>
      </div>
      <small>Click Confirm to apply changes to your student record.</small>`;
  } else if (x.status === "pending") {
    body = `<small>Verification Expired</small><b>${esc(x.approval_id)}</b><div>This request has expired. Please request the change again.</div>`;
  } else if (x.status === "executed") {
    body = `<small>Verified & Updated</small><b>${esc(x.approval_id)}</b><div>Your ${what} has been updated to <strong>${esc(x.new_value)}</strong>.</div>`;
  } else {
    body = `<small>Cancelled</small><b>${esc(x.approval_id)}</b><div>Change request was cancelled. No changes made.</div>`;
  }
  card.classList.toggle("ok", x.status === "executed");
  card.classList.toggle("rej", x.status === "rejected" || (x.status === "pending" && x.expired));
  card.innerHTML = `${icon(x.status === "executed" ? "check" : "shield")}<div>${body}<div class="confirm-error" role="alert"></div></div>`;
  card.querySelectorAll("button[data-d]").forEach((b) => (b.onclick = () => decide(x.approval_id, b.dataset.d, card)));
}

async function decide(id, decision, card) {
  document.querySelectorAll(`.confirm[data-apr="${id}"] button, .req-list button`).forEach((b) => (b.disabled = true));
  const r = await fetch(`/api/requests/${id}/decide`, { 
    method: "POST", 
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }) 
  });
  const d = await r.json();
  if (!r.ok) {
    const e = card && card.querySelector(".confirm-error");
    if (e) e.textContent = d.error;
  }
  document.querySelectorAll(".confirm").forEach(hydrateConfirm);
  loadAudit();
}

async function loadAudit() {
  const r = await fetch("/api/audit");
  if (!r.ok) return;
  const d = await r.json();
  $("chainBadge").textContent = d.chain_ok ? "Verified" : "Chain Broken";
  $("chainBadge").className = "badge-chain " + (d.chain_ok ? "good" : "bad");
  $("auditList").innerHTML = d.rows.length ? d.rows.map((a) => `<li>
    <span class="dec dec-${esc(a.decision)}">${esc(a.decision)}</span>
    <span>${esc(a.action)}${a.target && a.target !== a.actor_id ? " on " + esc(a.target) : ""}</span>
    <small>${esc(a.result)} • ${esc(a.ts.slice(11, 19))}</small>
  </li>`).join("") : '<li class="empty">No audit events recorded</li>';
}

function renderSidebarQuestions(filterCat = "all") {
  const list = $("examples");
  list.innerHTML = "";
  const filtered = filterCat === "all" ? QUICK : QUICK.filter(t => t.cat === filterCat);
  $("demoCounter").textContent = `${filtered.length} Prompts`;
  
  filtered.forEach((t) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <button type="button" title="${esc(t.desc)}">
        <div class="quick-btn-icon">${icon(t.icon)}</div>
        <div class="quick-btn-info">
          <span class="quick-btn-title">${esc(t.title)}</span>
          <span class="quick-btn-sub">${esc(t.tag)}</span>
        </div>
        <svg class="quick-btn-arrow" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>
      </button>
    `;
    li.querySelector("button").onclick = () => {
      closeMobileSidebar();
      send(t.q);
    };
    list.appendChild(li);
  });
}

function welcome() {
  const firstName = me.name ? me.name.replace(/\(.*?\)/g, "").trim().split(" ")[0] : "Student";
  
  $("chat").innerHTML = `
    <div class="welcome-container">
      <div class="welcome-hero">
        <h3>Welcome, ${esc(firstName)}</h3>
        <p>Your official student support desk. Ask about your fee status, scholarship renewals, attendance guidelines, or get verified help with your student record.</p>
        
        <div class="welcome-filter-chips">
          <button class="filter-chip active" data-cat="all">All</button>
          <button class="filter-chip" data-cat="finance">Fees & Balances</button>
          <button class="filter-chip" data-cat="scholarship">Scholarships</button>
          <button class="filter-chip" data-cat="academics">Academics</button>
          <button class="filter-chip" data-cat="support">Support</button>
        </div>
      </div>

      <div class="tiles-grid" id="tilesGrid"></div>
    </div>
  `;

  renderWelcomeTiles("all");

  // Wire category filter chips in hero
  $("chat").querySelectorAll(".filter-chip").forEach((btn) => {
    btn.onclick = () => {
      $("chat").querySelectorAll(".filter-chip").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      renderWelcomeTiles(btn.dataset.cat);
    };
  });
}

function renderWelcomeTiles(filterCat = "all") {
  const grid = $("tilesGrid");
  if (!grid) return;
  grid.innerHTML = "";
  const filtered = filterCat === "all" ? QUICK.slice(0, 6) : QUICK.filter(t => t.cat === filterCat);

  filtered.forEach((t) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "demo-tile";
    card.innerHTML = `
      <div class="tile-top">
        <div class="tile-icon-wrap">${icon(t.icon)}</div>
        <span class="tile-tag">${esc(t.tag)}</span>
      </div>
      <b>${esc(t.title)}</b>
      <span>${esc(t.desc)}</span>
    `;
    card.onclick = () => send(t.q);
    grid.appendChild(card);
  });
}

async function send(text) {
  text = (text || "").trim();
  if (!text || $("send").disabled) return;
  userMsg(text);
  $("send").disabled = true;
  const wait = document.createElement("div");
  wait.className = "row bot";
  wait.innerHTML = `<div class="who">${icon("bot")}</div><div class="col"><div class="bubble"><span class="dots" aria-label="Searching records"><i></i><i></i><i></i></span></div></div>`;
  $("chat").appendChild(wait);
  scrollDown();
  try {
    const r = await fetch("/api/chat", { 
      method: "POST", 
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history, session_id: sessionId }) 
    });
    const data = await r.json();
    wait.remove();
    if (r.status === 401) { showLogin("Your session has ended. Please log in again."); return; }
    if (!r.ok) botMsg(data.error || "That request could not be processed. Please try again.", null, true);
    else {
      history.push({ role: "user", content: text }, { role: "assistant", content: data.answer });
      botMsg(data.answer, data, !!data.error && data.error !== "max_steps_reached");
      loadMemory();
      loadAudit();
    }
  } catch (e) {
    wait.remove();
    botMsg("Unable to reach the backend server. Verify that python app.py is running and try again.", null, true);
  }
  $("send").disabled = false;
  $("msg").focus();
}

async function loadMemory() {
  const r = await fetch("/api/memory");
  if (!r.ok) return;
  const items = await r.json();
  if ($("sbMemCount")) $("sbMemCount").textContent = items.length;
  $("memList").innerHTML = items.length ? "" : '<li class="empty">No custom memory saved</li>';
  items.forEach((m) => {
    const li = document.createElement("li");
    li.innerHTML = `<span><b>${esc(m.key)}:</b> ${esc(m.value)}</span>`;
    const x = document.createElement("button");
    x.className = "x";
    x.textContent = "×";
    x.setAttribute("aria-label", `Forget ${m.key}`);
    x.onclick = async () => { await fetch(`/api/memory/${m.memory_id}`, { method: "DELETE" }); loadMemory(); };
    li.appendChild(x);
    $("memList").appendChild(li);
  });
}

function closeMobileSidebar() {
  const panel = $("sidePanel");
  const overlay = $("sidebarOverlay");
  if (panel) panel.classList.remove("open");
  if (overlay) overlay.classList.remove("active");
}

function newConversation() {
  closeMobileSidebar();
  history = [];
  sessionId = Math.random().toString(36).slice(2, 10);
  welcome();
}

function showLogin(message = "") {
  history = [];
  $("chat").innerHTML = "";
  $("memList").innerHTML = "";
  $("auditList").innerHTML = "";
  $("appView").classList.add("d-none");
  $("loginView").classList.remove("d-none");
  $("pw").value = "";
  $("loginErr").textContent = message;
  $("send").disabled = false;
}

function showApp(id, name) {
  me = { id, name: name || id };
  $("userName").textContent = me.name.replace(/\(.*?\)/g, "").trim();
  $("userId").textContent = id;
  $("userAvatar").textContent = initials(me.name);
  $("loginView").classList.add("d-none");
  $("appView").classList.remove("d-none");
  newConversation();
  loadMemory();
  loadAudit();
  renderSidebarQuestions("all");
  $("msg").focus();
}

// Login form submission handler
$("loginForm").onsubmit = async (e) => {
  e.preventDefault();
  $("loginErr").textContent = "";
  const r = await fetch("/api/login", { 
    method: "POST", 
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ student_id: $("sid").value, password: $("pw").value }) 
  });
  const d = await r.json();
  if (r.ok) showApp(d.student, d.name); else $("loginErr").textContent = d.error;
};

// 1-Click Interactive Login from Demo Profile Cards
document.querySelectorAll(".demo-row").forEach((b) => {
  b.onclick = async () => {
    $("sid").value = b.dataset.id;
    $("pw").value = b.dataset.pw;
    $("loginErr").textContent = "";
    const r = await fetch("/api/login", { 
      method: "POST", 
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ student_id: b.dataset.id, password: b.dataset.pw }) 
    });
    const d = await r.json();
    if (r.ok) showApp(d.student, d.name); else $("loginErr").textContent = d.error;
  };
});

$("logout").onclick = async () => { 
  closeMobileSidebar();
  await fetch("/api/logout", { method: "POST" }); 
  showLogin(); 
};
$("form").onsubmit = (e) => { e.preventDefault(); const t = $("msg").value; $("msg").value = ""; send(t); };
$("newChat").onclick = newConversation;
$("clearMem").onclick = async () => { await fetch("/api/memory", { method: "DELETE" }); loadMemory(); };

// Mobile responsive drawer toggle handlers
const sidebarToggle = $("sidebarToggle");
const sidebarOverlay = $("sidebarOverlay");
if (sidebarToggle) {
  sidebarToggle.onclick = () => {
    const panel = $("sidePanel");
    if (panel) {
      const isOpen = panel.classList.toggle("open");
      if (sidebarOverlay) sidebarOverlay.classList.toggle("active", isOpen);
    }
  };
}
if (sidebarOverlay) {
  sidebarOverlay.onclick = closeMobileSidebar;
}

// Sidebar navigation tabs (Questions, Memory, Audit Log)
document.querySelectorAll(".sidebar-tabs .sb-tab").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".sidebar-tabs .sb-tab").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const targetId = btn.dataset.pane;
    document.querySelectorAll(".sb-pane").forEach(pane => {
      pane.classList.toggle("d-none", pane.id !== targetId);
    });
  };
});

// Inline Memory Add Form
if ($("toggleAddMem")) {
  $("toggleAddMem").onclick = () => {
    const f = $("addMemForm");
    f.classList.toggle("d-none");
    if (!f.classList.contains("d-none")) $("memKey").focus();
  };
}

if ($("addMemForm")) {
  $("addMemForm").onsubmit = async (e) => {
    e.preventDefault();
    const key = $("memKey").value.trim();
    const val = $("memVal").value.trim();
    if (!key || !val) return;
    const r = await fetch("/api/memory", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value: val })
    });
    if (r.ok) {
      $("memKey").value = "";
      $("memVal").value = "";
      $("addMemForm").classList.add("d-none");
      loadMemory();
    }
  };
}

// Sidebar category filter tabs handler
document.querySelectorAll("#quickTabs .cat-tab").forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll("#quickTabs .cat-tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    renderSidebarQuestions(tab.dataset.cat);
  };
});

// Mobile viewport & keyboard scroll anchoring
const msgInput = $("msg");
function adaptMobileUI() {
  if (msgInput) {
    msgInput.placeholder = window.innerWidth <= 600 ? "Ask a question..." : "Ask about fees, courses, policies...";
  }
}
window.addEventListener("resize", adaptMobileUI);
adaptMobileUI();

if (msgInput) {
  msgInput.addEventListener("focus", () => {
    setTimeout(scrollDown, 250);
  });
}
if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", () => {
    if (document.activeElement === msgInput) {
      setTimeout(scrollDown, 100);
    }
  });
}

// Initialization
(async () => {
  const m = await (await fetch("/api/me")).json();
  if (m.student) showApp(m.student, m.name); else showLogin();
})();
