/**
 * Popup script – makes API calls directly.
 * No chrome.runtime.sendMessage is used (avoids MV3 messaging bugs).
 * State is persisted in chrome.storage.local so reopening the popup
 * shows the last result or loading state.
 */

const API_URL = "http://localhost:8000/api/verify";

// DOM refs
const claimInput        = document.getElementById("claimInput");
const verifyBtn         = document.getElementById("verifyBtn");
const loadingSection    = document.getElementById("loadingSection");
const resultSection     = document.getElementById("resultSection");
const errorSection      = document.getElementById("errorSection");
const verdictCard       = document.getElementById("verdictCard");
const verdictBadge      = document.getElementById("verdictBadge");
const verdictConfidence = document.getElementById("verdictConfidence");
const resultClaim       = document.getElementById("resultClaim");
const resultReasoning   = document.getElementById("resultReasoning");
const subClaimsBlock    = document.getElementById("subClaimsBlock");
const subClaimsList     = document.getElementById("subClaimsList");
const citationsBlock    = document.getElementById("citationsBlock");
const citationsList     = document.getElementById("citationsList");
const metaTime          = document.getElementById("metaTime");
const metaSources       = document.getElementById("metaSources");
const errorText         = document.getElementById("errorText");
const loaderSubtext     = document.getElementById("loaderSubtext");

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

function showSection(section) {
  [loadingSection, resultSection, errorSection].forEach(
    (s) => s && s.classList.add("hidden")
  );
  if (section) section.classList.remove("hidden");
}

function setLoading(on, msg) {
  if (verifyBtn) verifyBtn.disabled = on;
  if (on) {
    showSection(loadingSection);
    if (loaderSubtext && msg) loaderSubtext.textContent = msg;
  }
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

function renderResult(result) {
  showSection(resultSection);
  if (verifyBtn) verifyBtn.disabled = false;

  const v = result.verdict || "UNKNOWN";
  if (verdictCard)       verdictCard.className = "verdict-card verdict--" + v;
  if (verdictBadge)      verdictBadge.textContent = v.replace(/_/g, " ");
  if (verdictConfidence) verdictConfidence.textContent =
    Math.round((result.confidence || 0) * 100) + "% confidence";

  if (resultClaim)    resultClaim.textContent = result.claim || "";
  if (resultReasoning) resultReasoning.textContent =
    result.reasoning || "No reasoning provided.";

  // Sub-claims
  if (result.sub_claims && result.sub_claims.length) {
    if (subClaimsBlock) subClaimsBlock.style.display = "block";
    if (subClaimsList) {
      subClaimsList.innerHTML = "";
      result.sub_claims.forEach((sc) => {
        const d = document.createElement("div");
        d.className = "sub-claim-item";
        d.innerHTML =
          '<span class="sub-claim-item__verdict">[' +
          escapeHtml(sc.verdict) + "]</span> " + escapeHtml(sc.text);
        subClaimsList.appendChild(d);
      });
    }
  } else if (subClaimsBlock) {
    subClaimsBlock.style.display = "none";
  }

  // Citations
  if (result.citations && result.citations.length) {
    if (citationsBlock) citationsBlock.style.display = "block";
    if (citationsList) {
      citationsList.innerHTML = "";
      result.citations.forEach((c) => {
        const li = document.createElement("li");
        const cred = Math.round((c.credibility_score || 0) * 100);
        li.innerHTML =
          "<strong>" + escapeHtml(c.source_name) + "</strong>" +
          ' <span class="citation-cred">(' + cred + "% cred.)</span>" +
          (c.url
            ? '<br><a href="' + escapeHtml(c.url) + '" target="_blank">' +
              escapeHtml(c.url) + "</a>"
            : "") +
          (c.relevant_quote
            ? '<span class="citation-quote">"' +
              escapeHtml(c.relevant_quote.substring(0, 200)) + '"</span>'
            : "");
        citationsList.appendChild(li);
      });
    }
  } else if (citationsBlock) {
    citationsBlock.style.display = "none";
  }

  // Metadata
  const m = result.metadata || {};
  if (metaTime) metaTime.textContent = m.processing_time_ms
    ? (m.processing_time_ms / 1000).toFixed(1) + "s" : "";
  if (metaSources) metaSources.textContent = m.sources_checked
    ? m.sources_checked + " sources" : "";
}

function renderError(msg) {
  showSection(errorSection);
  if (errorText) errorText.textContent = msg;
  if (verifyBtn) verifyBtn.disabled = false;
}

// ---------------------------------------------------------------------------
// Verify – direct fetch (no service worker messaging)
// ---------------------------------------------------------------------------

async function verifyClaim(text) {
  if (!text || !text.trim()) return;
  const trimmed = text.trim();

  setLoading(true, "Searching knowledge base and web sources...");

  // Persist loading state so reopening popup shows spinner
  try {
    await chrome.storage.local.set({
      pendingClaim: trimmed,
      verificationResult: null,
      verificationStatus: "loading",
    });
  } catch (_) {}

  try {
    const resp = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: trimmed }),
    });

    if (!resp.ok) throw new Error("Server returned " + resp.status);

    const result = await resp.json();

    // Persist result
    try {
      await chrome.storage.local.set({
        verificationResult: result,
        verificationStatus: "done",
      });
    } catch (_) {}

    renderResult(result);
  } catch (err) {
    // Persist error
    try {
      await chrome.storage.local.set({
        verificationResult: null,
        verificationStatus: "error",
        verificationError: err.message,
      });
    } catch (_) {}

    renderError("Verification failed: " + err.message);
  }
}

// ---------------------------------------------------------------------------
// Poll storage (only used when the context-menu flow is running in the
// background service worker and the user opens the popup to see progress)
// ---------------------------------------------------------------------------

let pollTimer = null;

function startPolling() {
  stopPolling();
  pollTimer = setInterval(async () => {
    try {
      const d = await chrome.storage.local.get([
        "verificationResult",
        "verificationStatus",
        "verificationError",
      ]);
      if (d.verificationStatus === "done" && d.verificationResult) {
        stopPolling();
        renderResult(d.verificationResult);
      } else if (d.verificationStatus === "error") {
        stopPolling();
        renderError(d.verificationResult?.reasoning || d.verificationError || "Verification failed");
      }
    } catch (_) {}
  }, 500);
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

// ---------------------------------------------------------------------------
// Event listeners
// ---------------------------------------------------------------------------

verifyBtn.addEventListener("click", () => verifyClaim(claimInput.value));

claimInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    verifyClaim(claimInput.value);
  }
});

// ---------------------------------------------------------------------------
// On open: restore state from storage
// ---------------------------------------------------------------------------

(async () => {
  try {
    const d = await chrome.storage.local.get([
      "pendingClaim",
      "verificationResult",
      "verificationStatus",
      "verificationError",
    ]);

    if (d.pendingClaim) claimInput.value = d.pendingClaim;

    if (d.verificationStatus === "loading") {
      // A context-menu verification is running in the service worker
      setLoading(true, "Still verifying... please wait");
      startPolling();
    } else if (d.verificationStatus === "done" && d.verificationResult) {
      renderResult(d.verificationResult);
    } else if (d.verificationStatus === "error") {
      renderError(d.verificationResult?.reasoning || d.verificationError || "Verification failed");
    }
  } catch (_) {}
})();

window.addEventListener("unload", stopPolling);
