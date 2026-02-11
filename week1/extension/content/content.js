/**
 * Content script – shows popup notification near selected text.
 */

(() => {
  let lastSelection = null;

  // Store selection coordinates when user selects text
  document.addEventListener("mouseup", () => {
    const selection = window.getSelection();
    if (selection && selection.rangeCount > 0 && selection.toString().trim()) {
      const range = selection.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      lastSelection = {
        x: rect.left + rect.width / 2,  // center horizontally
        y: rect.top + window.scrollY,   // top of selection
      };
    }
  });

  // ---------------------------------------------------------------------------
  // Popup notification
  // ---------------------------------------------------------------------------
  function showPopup(message, type = "info") {
    // Remove any existing popup
    const existing = document.getElementById("cv-popup");
    if (existing) existing.remove();

    const popup = document.createElement("div");
    popup.id = "cv-popup";
    popup.className = `cv-popup cv-popup--${type}`;
    popup.innerHTML = `
      <div class="cv-popup__content">
        <span class="cv-popup__icon">${getIcon(type)}</span>
        <div class="cv-popup__body">
          <div class="cv-popup__text">${message}</div>
        </div>
        <button class="cv-popup__close" onclick="this.parentElement.parentElement.remove()">×</button>
      </div>
    `;

    document.body.appendChild(popup);

    // Position near the last selection
    if (lastSelection) {
      const popupRect = popup.getBoundingClientRect();
      const x = Math.max(10, Math.min(lastSelection.x - popupRect.width / 2, window.innerWidth - popupRect.width - 10));
      const y = Math.max(10, lastSelection.y - popupRect.height - 10); // 10px above selection

      popup.style.left = x + "px";
      popup.style.top = y + "px";
    } else {
      // Fallback: center top of screen
      popup.style.top = "80px";
      popup.style.left = "50%";
      popup.style.transform = "translateX(-50%)";
    }

    // Auto-dismiss after 10 seconds (except errors and loading)
    if (type !== "error" && type !== "loading") {
      setTimeout(() => {
        if (popup.parentElement) popup.remove();
      }, 10000);
    }
  }

  function getIcon(type) {
    switch (type) {
      case "loading":
        return "⏳";
      case "TRUE":
        return "✅";
      case "FALSE":
        return "❌";
      case "MISLEADING":
        return "⚠️";
      case "NOT_ENOUGH_EVIDENCE":
        return "❓";
      case "error":
        return "🚫";
      default:
        return "ℹ️";
    }
  }

  function verdictToType(verdict) {
    if (["TRUE", "FALSE", "MISLEADING", "NOT_ENOUGH_EVIDENCE"].includes(verdict)) {
      return verdict;
    }
    return "info";
  }

  // ---------------------------------------------------------------------------
  // Message handler
  // ---------------------------------------------------------------------------
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "VERIFY_STARTED") {
      showPopup(
        `<strong>Verifying claim...</strong><br>"${msg.text.substring(0, 100)}${msg.text.length > 100 ? "…" : ""}"`,
        "loading"
      );
    } else if (msg.type === "VERIFY_RESULT") {
      const r = msg.result;
      const verdict = r.verdict || "UNKNOWN";
      const confidence = Math.round((r.confidence || 0) * 100);
      const reasoning = (r.reasoning || "").substring(0, 200);
      const citations = r.citations?.length || 0;

      showPopup(
        `<strong style="font-size: 16px;">${verdict.replace(/_/g, " ")}</strong>` +
        `<div style="margin: 6px 0; font-size: 13px; opacity: 0.9;">${confidence}% confidence • ${citations} source${citations !== 1 ? "s" : ""}</div>` +
        `<div style="font-size: 13px; line-height: 1.4;">${reasoning}${reasoning.length >= 200 ? "…" : ""}</div>`,
        verdictToType(verdict)
      );
    } else if (msg.type === "VERIFY_ERROR") {
      showPopup(`<strong>Verification failed</strong><br>${msg.error}`, "error");
    }
  });
})();
