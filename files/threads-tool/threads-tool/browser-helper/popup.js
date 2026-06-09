const apiBaseInput = document.getElementById("apiBase");
const tokenInput = document.getElementById("token");
const statusEl = document.getElementById("status");

function setStatus(message, warn = false) {
  statusEl.textContent = message;
  statusEl.className = warn ? "status warn" : "status";
}

function normalizeApiBase(value) {
  return String(value || "http://localhost:8000/api").replace(/\/+$/, "");
}

function convertCookies(cookies) {
  return cookies.map((cookie) => ({
    domain: cookie.domain,
    expirationDate: cookie.expirationDate,
    hostOnly: cookie.hostOnly,
    httpOnly: cookie.httpOnly,
    name: cookie.name,
    path: cookie.path,
    sameSite: cookie.sameSite,
    secure: cookie.secure,
    session: cookie.session,
    value: cookie.value,
  }));
}

async function getThreadsCookies() {
  const cookies = await chrome.cookies.getAll({ domain: "threads.com" });
  const seen = new Set();
  return cookies.filter((cookie) => {
    const key = `${cookie.domain}|${cookie.path}|${cookie.name}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

async function loadState() {
  const state = await chrome.storage.local.get([
    "apiBase",
    "token",
    "threadsSearchDocId",
    "threadsSearchFriendlyName",
    "threadsSearchVariablesTemplate",
    "threadsDocIdCapturedAt",
  ]);
  apiBaseInput.value = state.apiBase || "http://localhost:8000/api";
  tokenInput.value = state.token || "";
  if (state.threadsSearchDocId) {
    setStatus(
      `Captured doc_id: ${state.threadsSearchDocId}\n${state.threadsSearchFriendlyName || ""}\n${state.threadsDocIdCapturedAt || ""}`
    );
  }
}

document.getElementById("openThreads").addEventListener("click", async () => {
  await chrome.tabs.create({
    url: "https://www.threads.com/search?q=threads&serp_type=default",
  });
  setStatus("Login if needed, then keep the search page open for a few seconds.");
});

document.getElementById("send").addEventListener("click", async () => {
  const apiBase = normalizeApiBase(apiBaseInput.value);
  const token = tokenInput.value.trim();
  await chrome.storage.local.set({ apiBase, token });

  if (!token) {
    setStatus("Missing app token.", true);
    return;
  }

  const cookies = await getThreadsCookies();
  if (!cookies.some((cookie) => cookie.name === "sessionid")) {
    setStatus("No Threads sessionid cookie found. Login to Threads first.", true);
    return;
  }

  const state = await chrome.storage.local.get([
    "threadsSearchDocId",
    "threadsSearchFriendlyName",
    "threadsSearchVariablesTemplate",
  ]);

  const response = await fetch(`${apiBase}/radar/session/browser-import`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      cookie: JSON.stringify(convertCookies(cookies)),
      search_doc_id: state.threadsSearchDocId || null,
      search_friendly_name: state.threadsSearchFriendlyName || null,
      search_variables_template: state.threadsSearchVariablesTemplate || null,
    }),
  });

  const text = await response.text();
  if (!response.ok) {
    let message = text || `HTTP ${response.status}`;
    try {
      const data = JSON.parse(text);
      message = data.detail || data.message || message;
    } catch {
      // keep raw message
    }
    setStatus(`Import failed: ${message}`, true);
    return;
  }

  setStatus(
    `Imported ${cookies.length} cookies.${state.threadsSearchDocId ? `\nSaved doc_id: ${state.threadsSearchDocId}${state.threadsSearchVariablesTemplate ? "\nSaved search variables template." : ""}` : "\nNo search doc_id captured yet."}`
  );
});

loadState();
