/**
 * Habit Tracker - Minimal Vanilla JavaScript
 * Provides progressive enhancement for weekday selector and daily toggles.
 */

document.addEventListener("DOMContentLoaded", () => {
  // 1. Weekday Selector Toggle in Habit Form
  const frequencySelect = document.getElementById("id_frequency");
  const weekdayContainer = document.getElementById("weekday-selector-container");

  if (frequencySelect && weekdayContainer) {
    const updateWeekdayVisibility = () => {
      if (frequencySelect.value === "WEEKDAYS") {
        weekdayContainer.style.display = "block";
      } else {
        weekdayContainer.style.display = "none";
      }
    };

    frequencySelect.addEventListener("change", updateWeekdayVisibility);
    updateWeekdayVisibility(); // Initial check on load
  }

  // 1b. Validation Rule / Rule Strategy Toggle in Habit Form
  const strategySelect = document.getElementById("id_rule_strategy_ref");
  const ruleSelect = document.getElementById("id_validation_rule");
  const timeContainer = document.getElementById("time-window-container");
  const numericContainer = document.getElementById("numeric-target-container");
  const evidenceContainer = document.getElementById("evidence-hint-container");
  const unitInput = document.getElementById("id_unit_label");

  let strategiesMeta = {};
  const metaElem = document.getElementById("rule-strategies-meta");
  if (metaElem) {
    try {
      strategiesMeta = JSON.parse(metaElem.textContent);
    } catch (e) {
      console.error("Failed to parse rule strategies meta", e);
    }
  }

  const updateStrategyVisibility = () => {
    let hasTime = false;
    let hasNumeric = false;
    let hasEvidence = false;

    if (strategySelect && strategySelect.value && strategiesMeta[strategySelect.value]) {
      const meta = strategiesMeta[strategySelect.value];
      const engine = meta.engine || "";
      hasTime = !!meta.has_time_window || engine === "TIME_WINDOW" || engine === "TIME_AND_EVIDENCE";
      hasNumeric = !!meta.requires_numeric || engine === "NUMERIC_TARGET";
      hasEvidence = !!meta.requires_evidence || engine === "EVIDENCE_FILE" || engine === "TIME_AND_EVIDENCE";
      if (meta.default_unit && unitInput && !unitInput.value.trim()) {
        unitInput.value = meta.default_unit;
      }
    } else if (ruleSelect) {
      const val = ruleSelect.value;
      hasTime = (val === "TIME_WINDOW" || val === "TIME_AND_EVIDENCE");
      hasNumeric = (val === "NUMERIC_TARGET");
      hasEvidence = (val === "EVIDENCE_FILE" || val === "TIME_AND_EVIDENCE");
    }

    if (timeContainer) {
      const hasTimeErrors = timeContainer.querySelector(".form-error");
      timeContainer.style.display = (hasTime || hasTimeErrors) ? "block" : "none";
    }
    if (numericContainer) {
      const hasNumericErrors = numericContainer.querySelector(".form-error");
      numericContainer.style.display = (hasNumeric || hasNumericErrors) ? "block" : "none";
    }
    if (evidenceContainer) evidenceContainer.style.display = hasEvidence ? "block" : "none";
  };

  if (strategySelect) {
    strategySelect.addEventListener("change", updateStrategyVisibility);
    updateStrategyVisibility();
  }
  if (ruleSelect) {
    ruleSelect.addEventListener("change", updateStrategyVisibility);
    if (!strategySelect) updateStrategyVisibility();
  }

  // 1c. Pixel Score Dynamic Allotment in Habit Form
  const habitTypeSelect = document.getElementById("id_habit_type");
  const pixelScoreInput = document.getElementById("id_pixel_score");
  const pixelScoreBadgeVal = document.getElementById("pixel-score-badge-val");

  if (pixelScoreInput && pixelScoreBadgeVal) {
    const updatePixelScoreBadge = () => {
      const val = parseInt(pixelScoreInput.value, 10);
      pixelScoreBadgeVal.textContent = isNaN(val) || val < 1 ? "2" : val;
    };

    pixelScoreInput.addEventListener("input", updatePixelScoreBadge);

    if (habitTypeSelect) {
      let previousType = habitTypeSelect.value;
      const onHabitTypeChange = () => {
        const currentType = habitTypeSelect.value;
        if (currentType === "GENERAL") {
          pixelScoreInput.value = "2";
          pixelScoreInput.readOnly = true;
          pixelScoreInput.style.backgroundColor = "var(--surface-raised)";
          pixelScoreInput.style.cursor = "not-allowed";
        } else if (currentType === "PREDEFINED_PURPOSE") {
          pixelScoreInput.readOnly = false;
          pixelScoreInput.style.backgroundColor = "";
          pixelScoreInput.style.cursor = "text";
          if (previousType === "GENERAL" || pixelScoreInput.value === "2" || pixelScoreInput.value === "10" || !pixelScoreInput.value) {
            pixelScoreInput.value = "5";
          }
        } else if (currentType === "EXPERT_PRESCRIBED") {
          pixelScoreInput.readOnly = false;
          pixelScoreInput.style.backgroundColor = "";
          pixelScoreInput.style.cursor = "text";
          if (previousType === "GENERAL" || pixelScoreInput.value === "2" || pixelScoreInput.value === "5" || !pixelScoreInput.value) {
            pixelScoreInput.value = "10";
          }
        }
        previousType = currentType;
        updatePixelScoreBadge();
      };

      habitTypeSelect.addEventListener("change", onHabitTypeChange);
      if (habitTypeSelect.value === "GENERAL") {
        pixelScoreInput.value = "2";
        pixelScoreInput.readOnly = true;
        pixelScoreInput.style.backgroundColor = "var(--surface-raised)";
        pixelScoreInput.style.cursor = "not-allowed";
      }
      updatePixelScoreBadge();
    }
  }

  // 2. Alert Dismissal
  const alerts = document.querySelectorAll(".alert");
  alerts.forEach((alert) => {
    const closeBtn = alert.querySelector(".alert-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        alert.style.opacity = "0";
        setTimeout(() => alert.remove(), 200);
      });
    }
  });

  // 3. Progressive Enhancement for Habit Completion Forms
  const completionForms = document.querySelectorAll(".ajax-completion-form");
  completionForms.forEach((form) => {
    form.addEventListener("submit", async (e) => {
      // If Javascript is supported, enhance completion toggle smoothly
      e.preventDefault();
      const submitBtn = form.querySelector("button[type='submit']");
      if (submitBtn) submitBtn.disabled = true;

      try {
        const formData = new FormData(form);
        let apiUrl = form.action;
        const completeMatch = form.action.match(/\/habits\/(\d+)\/complete\/?/);
        const undoMatch = form.action.match(/\/habits\/(\d+)\/undo\/?/);
        if (completeMatch) {
          apiUrl = `/api/v1/habits/${completeMatch[1]}/complete/`;
        } else if (undoMatch) {
          apiUrl = `/api/v1/habits/${undoMatch[1]}/undo/`;
        }

        const response = await fetch(apiUrl, {
          method: "POST",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": formData.get("csrfmiddlewaretoken"),
          },
          body: formData,
        });

        const result = await response.json().catch(() => null);
        if (response.ok && result && result.success) {
          console.info("[HabitPulse REST API] Success:", apiUrl, result);
          window.location.reload();
        } else {
          const errMsg = (result && result.error) ? result.error : "Failed to update habit.";
          alert(errMsg);
          if (submitBtn) submitBtn.disabled = false;
        }
      } catch (err) {
        form.submit();
      }
    });
  });

  // 3b. Habit Completion Verification Modal
  const modal = document.getElementById("habit-verification-modal");
  if (modal) {
    const modalForm = document.getElementById("verification-form");
    const modalTitle = document.getElementById("modal-habit-title");
    const modalSubtitle = document.getElementById("modal-habit-subtitle");
    const modalNumericGroup = document.getElementById("modal-numeric-group");
    const modalLoggedValue = document.getElementById("modal-logged-value");
    const modalUnitBadge = document.getElementById("modal-unit-badge");
    const modalNumericHelp = document.getElementById("modal-numeric-help");
    const modalEvidenceGroup = document.getElementById("modal-evidence-group");
    const modalEvidenceFile = document.getElementById("modal-evidence-file");
    const modalAlert = document.getElementById("modal-alert");
    const closeBtn = document.getElementById("close-verification-modal");
    const cancelBtn = document.getElementById("cancel-verification-modal");

    const closeModal = () => {
      modal.classList.remove("open");
      setTimeout(() => {
        modal.style.display = "none";
      }, 150);
      if (modalAlert) {
        modalAlert.style.display = "none";
        modalAlert.textContent = "";
      }
      if (modalForm) modalForm.reset();
    };

    const openModal = (btn) => {
      const habitName = btn.getAttribute("data-habit-name") || "Habit";
      const actionUrl = btn.getAttribute("data-action-url") || "";
      const requiresEvidence = btn.getAttribute("data-requires-evidence") === "true";
      const requiresNumeric = btn.getAttribute("data-requires-numeric") === "true";
      const targetValue = btn.getAttribute("data-target-value") || "";
      const unitLabel = btn.getAttribute("data-unit-label") || "";
      const ruleDesc = btn.getAttribute("data-rule-desc") || "Verify completion";

      if (modalTitle) modalTitle.textContent = `Complete: ${habitName}`;
      if (modalSubtitle) modalSubtitle.textContent = ruleDesc;
      if (modalForm) modalForm.action = actionUrl;

      // Handle numeric fields
      if (modalNumericGroup) {
        if (requiresNumeric) {
          modalNumericGroup.style.display = "block";
          if (modalLoggedValue) {
            modalLoggedValue.required = true;
            modalLoggedValue.placeholder = `Target: ${targetValue} ${unitLabel}`;
          }
          if (modalUnitBadge) modalUnitBadge.textContent = unitLabel || "metric";
          if (modalNumericHelp) modalNumericHelp.textContent = `Goal threshold: at least ${targetValue} ${unitLabel}`;
        } else {
          modalNumericGroup.style.display = "none";
          if (modalLoggedValue) modalLoggedValue.required = false;
        }
      }

      // Handle evidence upload fields
      if (modalEvidenceGroup) {
        if (requiresEvidence) {
          modalEvidenceGroup.style.display = "block";
          if (modalEvidenceFile) modalEvidenceFile.required = true;
        } else {
          modalEvidenceGroup.style.display = "none";
          if (modalEvidenceFile) modalEvidenceFile.required = false;
        }
      }

      if (modalAlert) {
        modalAlert.style.display = "none";
        modalAlert.textContent = "";
      }

      modal.style.display = "flex";
      requestAnimationFrame(() => {
        modal.classList.add("open");
      });
    };

    document.querySelectorAll(".open-completion-modal").forEach((btn) => {
      btn.addEventListener("click", () => openModal(btn));
    });

    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);

    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeModal();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modal.classList.contains("open")) {
        closeModal();
      }
    });

    // AJAX form submission for verification modal
    if (modalForm) {
      modalForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const submitBtn = document.getElementById("submit-verification-btn");
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.textContent = "Verifying...";
        }

        try {
          const formData = new FormData(modalForm);
          let apiUrl = modalForm.action;
          const completeMatch = modalForm.action.match(/\/habits\/(\d+)\/complete\/?/);
          if (completeMatch) {
            apiUrl = `/api/v1/habits/${completeMatch[1]}/complete/`;
          }
          const response = await fetch(apiUrl, {
            method: "POST",
            headers: {
              "X-Requested-With": "XMLHttpRequest",
              "X-CSRFToken": formData.get("csrfmiddlewaretoken"),
            },
            body: formData,
          });

          if (response.ok) {
            window.location.reload();
          } else {
            const data = await response.json().catch(() => null);
            const errText = (data && data.error) ? data.error : "Failed to verify completion. Please check requirements.";
            if (modalAlert) {
              modalAlert.textContent = errText;
              modalAlert.style.display = "block";
            } else {
              alert(errText);
            }
            if (submitBtn) {
              submitBtn.disabled = false;
              submitBtn.textContent = "✓ Submit & Complete";
            }
          }
        } catch (err) {
          modalForm.submit();
        }
      });
    }
  }

  // 4. Navigation & Dropdown Toggle
  const closeAllDropdowns = () => {
    document.querySelectorAll(".dropdown-menu.show").forEach((m) => m.classList.remove("show"));
  };

  const dropdownToggles = document.querySelectorAll(".dropdown-toggle");
  dropdownToggles.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const parentDropdown = btn.closest(".dropdown");
      const menu = parentDropdown ? parentDropdown.querySelector(".dropdown-menu") : null;
      if (menu) {
        const isOpen = menu.classList.contains("show");
        // Close all open dropdowns first
        closeAllDropdowns();
        if (!isOpen) {
          menu.classList.add("show");
        }
      }
    });
  });

  // Close dropdowns on outside click or Escape key
  document.addEventListener("click", () => {
    closeAllDropdowns();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeAllDropdowns();
    }
  });

  // 5. Theme Switcher System
  const themeIcons = {
    ice: "❄️",
    light: "☀️",
    rose: "🌸",
    dark: "🌙"
  };

  const applyTheme = (themeName) => {
    document.documentElement.setAttribute("data-theme", themeName);
    localStorage.setItem("habitpulse_theme", themeName);

    // Update active checkmarks for button options
    document.querySelectorAll(".theme-option").forEach((opt) => {
      if (opt.getAttribute("data-theme-value") === themeName) {
        opt.classList.add("active");
      } else {
        opt.classList.remove("active");
      }
    });

    // Update theme select inputs if present
    document.querySelectorAll(".theme-select-control").forEach((sel) => {
      sel.value = themeName;
    });

    // Update icons on toggle buttons and labels
    document.querySelectorAll(".theme-icon").forEach((el) => {
      if (themeIcons[themeName]) {
        el.textContent = themeIcons[themeName];
      }
    });
  };

  // Initialize theme state
  const activeSavedTheme = localStorage.getItem("habitpulse_theme") || "ice";
  applyTheme(activeSavedTheme);

  // Bind click handlers for button-based theme options
  document.querySelectorAll(".theme-option").forEach((opt) => {
    opt.addEventListener("click", (e) => {
      e.preventDefault();
      const selectedTheme = opt.getAttribute("data-theme-value");
      if (selectedTheme) {
        applyTheme(selectedTheme);
      }
      closeAllDropdowns();
    });
  });

  // Bind change handlers for select-based theme dropdown
  document.querySelectorAll(".theme-select-control").forEach((sel) => {
    sel.addEventListener("click", (e) => {
      e.stopPropagation();
    });
    sel.addEventListener("change", (e) => {
      const selectedTheme = e.target.value;
      if (selectedTheme) {
        applyTheme(selectedTheme);
      }
      closeAllDropdowns();
    });
  });

  // 6. Global Password Visibility Toggle
  const EYE_ICON_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;
  const EYE_OFF_ICON_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>`;

  document.querySelectorAll(".password-toggle-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const targetId = btn.getAttribute("data-target");
      const wrapper = btn.closest(".password-input-wrapper");
      const input = targetId ? document.getElementById(targetId) : (wrapper ? wrapper.querySelector("input") : null);
      if (input) {
        const isPassword = input.getAttribute("type") === "password";
        input.setAttribute("type", isPassword ? "text" : "password");
        btn.innerHTML = isPassword ? EYE_OFF_ICON_SVG : EYE_ICON_SVG;
        btn.setAttribute("title", isPassword ? "Hide password" : "Show password");
        btn.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
      }
    });
  });

  // 7. Habits Hub 3-Section Sub Header Tabs
  const habitTabButtons = document.querySelectorAll(".habit-sub-header-btn");
  const habitSections = document.querySelectorAll(".habit-section");

  if (habitTabButtons.length > 0 && habitSections.length > 0) {
    const activateTab = (targetId) => {
      // Normalize targetId
      let normalizedId = targetId;
      if (targetId === "user_created" || targetId === "user-created") normalizedId = "my-habits";
      if (targetId === "predefined") normalizedId = "predefined-habits";
      if (targetId === "expert") normalizedId = "expert-habits";

      habitTabButtons.forEach((btn) => {
        const isMatch = btn.getAttribute("data-target") === normalizedId;
        btn.classList.toggle("active", isMatch);
        btn.setAttribute("aria-selected", isMatch ? "true" : "false");
      });

      habitSections.forEach((sec) => {
        const isMatch = sec.id === normalizedId;
        sec.classList.toggle("active", isMatch);
      });
    };

    habitTabButtons.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const targetId = btn.getAttribute("data-target");
        if (targetId) {
          activateTab(targetId);
          if (window.history && window.history.replaceState) {
            window.history.replaceState(null, "", `#${targetId}`);
          } else {
            window.location.hash = `#${targetId}`;
          }
        }
      });
    });

    // Handle hash on load or popstate
    const handleUrlHash = () => {
      const hash = window.location.hash.replace("#", "");
      if (hash && (hash === "my-habits" || hash === "predefined-habits" || hash === "expert-habits" || hash === "user-created" || hash === "predefined" || hash === "expert")) {
        activateTab(hash);
      } else {
        const urlParams = new URLSearchParams(window.location.search);
        const tabParam = urlParams.get("tab");
        if (tabParam) {
          activateTab(tabParam);
        }
      }
    };

    handleUrlHash();
    window.addEventListener("hashchange", handleUrlHash);
  }

  // 8. Idempotent Form Submission & Multi-Click Debouncing
  document.querySelectorAll(".js-idempotent-form, #habit-form").forEach((form) => {
    form.addEventListener("submit", function (e) {
      if (form.dataset.submitting === "true") {
        e.preventDefault();
        return false;
      }

      const submitBtn = form.querySelector("button[type='submit']");
      if (submitBtn) {
        form.dataset.submitting = "true";
        const originalText = submitBtn.innerHTML;
        submitBtn.dataset.originalText = originalText;

        let loadingText = "Saving...";
        const lower = originalText.toLowerCase();
        if (lower.includes("create")) {
          loadingText = "Creating Habit...";
        } else if (lower.includes("publish")) {
          loadingText = "Publishing...";
        } else if (lower.includes("add")) {
          loadingText = "Adding...";
        }

        submitBtn.disabled = true;
        submitBtn.style.opacity = "0.75";
        submitBtn.style.cursor = "not-allowed";
        submitBtn.innerHTML = `<span style="display: inline-block; width: 13px; height: 13px; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; vertical-align: middle; margin-right: 6px; animation: spin 0.75s linear infinite;"></span>${loadingText}`;
      }
    });
  });

  // 9. Client Timezone Synchronization for Accurate Time Window Validation
  try {
    const clientTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (clientTz) {
      const match = document.cookie.match(/(?:^|; )django_timezone=([^;]*)/);
      const currentTzCookie = match ? decodeURIComponent(match[1]) : null;
      if (currentTzCookie !== clientTz) {
        document.cookie = `django_timezone=${encodeURIComponent(clientTz)}; path=/; max-age=31536000; SameSite=Lax`;
      }
    }
  } catch (e) {
    // Graceful fallback if Intl API is unavailable
  }

  // 10. Live Dynamic Time Window Status & Real-Time Activation
  const updateTimeWindowHabits = () => {
    const containers = document.querySelectorAll('.habit-action-container[data-has-time-window="true"]');
    if (!containers.length) return;

    const now = new Date();
    const currentSeconds = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();

    containers.forEach((container) => {
      const startStr = container.getAttribute("data-window-start");
      const endStr = container.getAttribute("data-window-end");
      const startDisplay = container.getAttribute("data-window-start-display") || startStr;
      const endDisplay = container.getAttribute("data-window-end-display") || endStr;

      if (!startStr || !endStr) return;

      const [sh, sm, ss = 0] = startStr.split(":").map(Number);
      const [eh, em, es = 0] = endStr.split(":").map(Number);

      const startSeconds = sh * 3600 + sm * 60 + ss;
      // Minute inclusive: if end time seconds is 0, include up to 59 seconds of that minute
      const endSeconds = eh * 3600 + em * 60 + (es === 0 ? 59 : es);

      const lockedBtn = container.querySelector(".time-window-locked-btn");
      const statusText = container.querySelector(".time-window-status-text");
      const activeAction = container.querySelector(".time-window-active-action");

      if (currentSeconds < startSeconds) {
        // Locked: too early
        if (lockedBtn) {
          lockedBtn.style.display = "inline-block";
          if (statusText) statusText.textContent = `Locked until ${startDisplay}`;
          lockedBtn.title = `Locked until ${startDisplay}`;
        }
        if (activeAction) activeAction.style.display = "none";
      } else if (currentSeconds <= endSeconds) {
        // Active: inside allowed window! Real-time activation without page reload
        if (lockedBtn) lockedBtn.style.display = "none";
        if (activeAction) activeAction.style.display = "inline-block";
      } else {
        // Expired: window closed
        if (lockedBtn) {
          lockedBtn.style.display = "inline-block";
          if (statusText) statusText.textContent = `Window closed at ${endDisplay}`;
          lockedBtn.title = `Window closed at ${endDisplay}`;
        }
        if (activeAction) activeAction.style.display = "none";
      }
    });
  };

  // Run on load and every second for instantaneous real-time UI transitions
  updateTimeWindowHabits();
  setInterval(updateTimeWindowHabits, 1000);
// 11. Dashboard Live API Telemetry & Network Diagnostics
  if (window.location.pathname === "/" || window.location.pathname.startsWith("/dashboard")) {
    const urlParams = new URLSearchParams(window.location.search);
    const scope = urlParams.get("scope") || "";
    const apiUrl = `/api/v1/dashboard/${scope ? `?scope=${encodeURIComponent(scope)}` : ""}`;
    fetch(apiUrl, {
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    })
      .then((res) => res.json())
      .then((data) => {
        console.info("[HabitPulse API] Dashboard synchronized via Network:", data);
      })
      .catch((err) => {
        console.debug("[HabitPulse API] Dashboard sync idle", err);
      });
  }

  // 12. Users Directory API Telemetry
  if (window.location.pathname.includes("/admin-panel/users")) {
    fetch("/api/v1/users/", {
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    })
      .then((res) => res.json())
      .then((data) => {
        console.info("[HabitPulse API] User directory synchronized via Network:", data);
      })
      .catch((err) => {
        console.debug("[HabitPulse API] Users sync idle", err);
      });
  }
});
