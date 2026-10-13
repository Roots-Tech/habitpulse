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

  // 1b. Validation Rule Toggle in Habit Form
  const ruleSelect = document.getElementById("id_validation_rule");
  const timeContainer = document.getElementById("time-window-container");
  const numericContainer = document.getElementById("numeric-target-container");
  const evidenceContainer = document.getElementById("evidence-hint-container");

  if (ruleSelect) {
    const updateValidationRuleVisibility = () => {
      const val = ruleSelect.value;
      if (timeContainer) {
        timeContainer.style.display = (val === "TIME_WINDOW" || val === "TIME_AND_EVIDENCE") ? "block" : "none";
      }
      if (numericContainer) {
        numericContainer.style.display = (val === "NUMERIC_TARGET") ? "block" : "none";
      }
      if (evidenceContainer) {
        evidenceContainer.style.display = (val === "EVIDENCE_FILE" || val === "TIME_AND_EVIDENCE") ? "block" : "none";
      }
    };

    ruleSelect.addEventListener("change", updateValidationRuleVisibility);
    updateValidationRuleVisibility(); // Initial check on load
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
        const response = await fetch(form.action, {
          method: "POST",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": formData.get("csrfmiddlewaretoken"),
          },
          body: formData,
        });

        if (response.ok) {
          // Reload current page state seamlessly to refresh calendar & streak widgets
          window.location.reload();
        } else {
          // Fallback to normal form submit on error
          form.submit();
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
          const response = await fetch(modalForm.action, {
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

  // 4. Admin Panel Dropdown Toggle
  const dropdownToggles = document.querySelectorAll(".dropdown-toggle");
  dropdownToggles.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const parentDropdown = btn.closest(".dropdown");
      const menu = parentDropdown.querySelector(".dropdown-menu");
      if (menu) {
        const isOpen = menu.classList.contains("show");
        // Close all open dropdowns first
        document.querySelectorAll(".dropdown-menu.show").forEach((m) => m.classList.remove("show"));
        if (!isOpen) {
          menu.classList.add("show");
        }
      }
    });
  });

  // Close dropdowns on outside click or Escape key
  document.addEventListener("click", () => {
    document.querySelectorAll(".dropdown-menu.show").forEach((m) => m.classList.remove("show"));
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".dropdown-menu.show").forEach((m) => m.classList.remove("show"));
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

    // Update active checkmarks
    document.querySelectorAll(".theme-option").forEach((opt) => {
      if (opt.getAttribute("data-theme-value") === themeName) {
        opt.classList.add("active");
      } else {
        opt.classList.remove("active");
      }
    });

    // Update icons on toggle buttons
    document.querySelectorAll(".theme-icon").forEach((el) => {
      if (themeIcons[themeName]) {
        el.textContent = themeIcons[themeName];
      }
    });
  };

  // Initialize theme state
  const activeSavedTheme = localStorage.getItem("habitpulse_theme") || "ice";
  applyTheme(activeSavedTheme);

  // Bind click handlers
  document.querySelectorAll(".theme-option").forEach((opt) => {
    opt.addEventListener("click", (e) => {
      e.preventDefault();
      const selectedTheme = opt.getAttribute("data-theme-value");
      if (selectedTheme) {
        applyTheme(selectedTheme);
      }
      document.querySelectorAll(".dropdown-menu.show").forEach((m) => m.classList.remove("show"));
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
});
