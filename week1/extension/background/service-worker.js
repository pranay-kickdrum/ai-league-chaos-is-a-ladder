/**
 * Background service worker – ONLY handles context menu verification.
 * The popup handles its own API calls directly.
 * Shared state lives in chrome.storage.local.
 */

const API_URL = "http://localhost:8000/api/verify";

// Suppress stale‑port errors Chrome fires internally
self.addEventListener("unhandledrejection", (e) => e.preventDefault());

// ---------------------------------------------------------------------------
// Context menu setup
// ---------------------------------------------------------------------------

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "verify-claim",
      title: 'Verify Claim: "%s"',
      contexts: ["selection"],
    });
  });
});

// ---------------------------------------------------------------------------
// Context menu click → verify in background
// ---------------------------------------------------------------------------

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "verify-claim" || !info.selectionText) return;

  const text = info.selectionText.trim();
  const pageUrl = tab?.url || "";

  // Write loading state so popup can pick it up
  await chrome.storage.local.set({
    pendingClaim: text,
    pendingUrl: pageUrl,
    verificationResult: null,
    verificationStatus: "loading",
  }).catch(() => {});

  // Toast on page
  if (tab?.id) {
    chrome.tabs.sendMessage(tab.id, {
      type: "VERIFY_STARTED",
      text,
    }).catch(() => {});
  }

  // Call API
  try {
    const resp = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, url: pageUrl }),
    });

    if (!resp.ok) throw new Error(`API returned ${resp.status}`);
    const result = await resp.json();

    await chrome.storage.local.set({
      verificationResult: result,
      verificationStatus: "done",
    }).catch(() => {});

    if (tab?.id) {
      chrome.tabs.sendMessage(tab.id, {
        type: "VERIFY_RESULT",
        result,
      }).catch(() => {});
    }
  } catch (err) {
    const errorResult = {
      claim: text,
      verdict: "ERROR",
      confidence: 0,
      reasoning: `Verification failed: ${err.message}`,
      citations: [],
      sub_claims: [],
      metadata: {},
    };

    await chrome.storage.local.set({
      verificationResult: errorResult,
      verificationStatus: "error",
    }).catch(() => {});

    if (tab?.id) {
      chrome.tabs.sendMessage(tab.id, {
        type: "VERIFY_ERROR",
        error: err.message,
      }).catch(() => {});
    }
  }
});
