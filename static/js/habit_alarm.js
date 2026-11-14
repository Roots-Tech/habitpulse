/**
 * HabitPulse Habit Alarm & Free Intimation System
 * Supports:
 * 1. Native Web Push Notifications (via Service Worker)
 * 2. In-App Web Audio Alarm Chimes (Zero-asset oscillator)
 * 3. Client-side Real-time Alarm Scheduler & Snooze System
 * 4. 1-Click Phone Calendar (.ics) Native Alarm Sync
 */

(function () {
  'use strict';

  // -------------------------------------------------------------------------
  // 1. Web Audio Alarm Chime Generator (Pure Web Audio API - Zero External MP3)
  // -------------------------------------------------------------------------
  var audioCtx = null;

  function getAudioContext() {
    if (!audioCtx) {
      var AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        audioCtx = new AudioContextClass();
      }
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    return audioCtx;
  }

  function playAlarmChime() {
    try {
      var ctx = getAudioContext();
      if (!ctx) return;

      var now = ctx.currentTime;
      var notes = [
        { freq: 523.25, start: 0.0, dur: 0.18 }, // C5
        { freq: 659.25, start: 0.18, dur: 0.18 }, // E5
        { freq: 783.99, start: 0.36, dur: 0.35 }  // G5
      ];

      notes.forEach(function (n) {
        var osc = ctx.createOscillator();
        var gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(n.freq, now + n.start);

        gain.gain.setValueAtTime(0, now + n.start);
        gain.gain.linearRampToValueAtTime(0.25, now + n.start + 0.04);
        gain.gain.exponentialRampToValueAtTime(0.001, now + n.start + n.dur);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(now + n.start);
        osc.stop(now + n.start + n.dur);
      });
    } catch (e) {
      console.warn('[HabitAlarm] Audio playback unavailable:', e);
    }
  }

  // Helper: Convert VAPID base64 string to Uint8Array for PushManager
  function urlB64ToUint8Array(base64String) {
    var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    var rawData = window.atob(base64);
    var outputArray = new Uint8Array(rawData.length);
    for (var i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  // -------------------------------------------------------------------------
  // 2. Web Push Registration (Free Native Push)
  // -------------------------------------------------------------------------
  function setupWebPushSubscription() {
    var vapidMeta = document.querySelector('meta[name="vapid-public-key"]');
    var vapidKey = vapidMeta ? vapidMeta.getAttribute('content') : '';

    if (!vapidKey || !('serviceWorker' in navigator) || !('PushManager' in window)) {
      return;
    }

    if (Notification.permission !== 'granted') {
      return;
    }

    navigator.serviceWorker.ready.then(function (reg) {
      return reg.pushManager.getSubscription().then(function (sub) {
        if (sub) {
          return sendSubscriptionToServer(sub);
        }
        return reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlB64ToUint8Array(vapidKey)
        }).then(function (newSub) {
          return sendSubscriptionToServer(newSub);
        });
      });
    }).catch(function (err) {
      console.log('[HabitAlarm] Push registration notice:', err);
    });
  }

  function sendSubscriptionToServer(subscription) {
    var key = subscription.getKey ? subscription.getKey('p256dh') : null;
    var auth = subscription.getKey ? subscription.getKey('auth') : null;

    var p256dh = key ? btoa(String.fromCharCode.apply(null, new Uint8Array(key))) : '';
    var authKey = auth ? btoa(String.fromCharCode.apply(null, new Uint8Array(auth))) : '';

    var csrfToken = getCsrfToken();

    return fetch('/api/v1/push/subscribe/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({
        endpoint: subscription.endpoint,
        keys: {
          p256dh: p256dh,
          auth: authKey
        }
      })
    }).catch(function (e) {
      console.warn('[HabitAlarm] Failed to save push subscription:', e);
    });
  }

  function getCsrfToken() {
    var cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
    if (cookieMatch) return cookieMatch[1];
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  // -------------------------------------------------------------------------
  // 3. Floating Alarm Alert Banner
  // -------------------------------------------------------------------------
  function showFloatingAlarm(habit) {
    var container = document.getElementById('habit-alarm-toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'habit-alarm-toast-container';
      container.style.cssText = 'position: fixed; top: 1.25rem; right: 1.25rem; z-index: 999999; display: flex; flex-direction: column; gap: 0.75rem; max-width: 380px; width: 92%; pointer-events: none;';
      document.body.appendChild(container);
    }

    // Check if toast for this habit already visible
    var existing = document.getElementById('alarm-toast-' + habit.id);
    if (existing) return;

    var toast = document.createElement('div');
    toast.id = 'alarm-toast-' + habit.id;
    toast.style.cssText = 'pointer-events: auto; background: var(--surface-raised, #1e293b); color: var(--text-main, #f8fafc); border: 1.5px solid #f59e0b; border-radius: 12px; padding: 1rem 1.15rem; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 0 15px rgba(245, 158, 11, 0.25); animation: habitAlarmSlideIn 0.3s ease; position: relative;';

    toast.innerHTML = [
      '<div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.4rem;">',
      '  <div style="display: flex; align-items: center; gap: 0.5rem;">',
      '    <span style="font-size: 1.25rem; animation: habitBellRing 1.5s infinite;">⏰</span>',
      '    <strong style="font-size: 0.95rem; color: #fbbf24;">Habit Alarm Intimation</strong>',
      '  </div>',
      '  <button type="button" class="close-alarm-toast-btn" style="background: none; border: none; color: var(--text-muted, #94a3b8); font-size: 1.2rem; cursor: pointer; padding: 0 0.2rem; line-height: 1;">&times;</button>',
      '</div>',
      '<div style="font-size: 0.88rem; font-weight: 700; margin-bottom: 0.25rem;">' + escapeHtml(habit.name) + '</div>',
      '<p style="font-size: 0.78rem; color: var(--text-muted, #94a3b8); line-height: 1.4; margin: 0 0 0.75rem 0;">',
      '  Time to complete your habit! Preserve your consistency streak and earn <strong>' + (habit.pixel_score || 2) + ' pixels</strong>.',
      '</p>',
      '<div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">',
      '  <button type="button" class="alarm-done-btn btn btn-sm btn-primary" style="font-size: 0.75rem; padding: 0.3rem 0.65rem;">✅ Mark Done</button>',
      '  <button type="button" class="alarm-snooze-btn btn btn-sm btn-outline" style="font-size: 0.75rem; padding: 0.3rem 0.65rem;">⏳ Snooze 1h</button>',
      '  <button type="button" class="alarm-dismiss-btn btn btn-sm btn-ghost" style="font-size: 0.75rem; padding: 0.3rem 0.5rem;">Dismiss</button>',
      '</div>'
    ].join('');

    container.appendChild(toast);

    // Event listeners
    toast.querySelector('.close-alarm-toast-btn').onclick = function () { toast.remove(); };
    toast.querySelector('.alarm-dismiss-btn').onclick = function () { toast.remove(); };

    toast.querySelector('.alarm-done-btn').onclick = function () {
      fetch('/api/v1/habits/' + habit.id + '/complete/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCsrfToken(),
          'X-Requested-With': 'XMLHttpRequest'
        }
      }).then(function (r) { return r.json(); })
        .then(function (res) {
          toast.remove();
          if (res.success || res.status === 'success') {
            window.location.reload();
          }
        }).catch(function () {
          window.location.href = '/habits/' + habit.id + '/complete/';
        });
    };

    toast.querySelector('.alarm-snooze-btn').onclick = function () {
      fetch('/api/v1/habits/' + habit.id + '/reminder/snooze/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({ minutes: 60 })
      }).then(function () {
        toast.remove();
      });
    };
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  // -------------------------------------------------------------------------
  // 4. Real-time Alarm Poller & Local Intimation Dispatcher
  // -------------------------------------------------------------------------
  var alertedAlarmsMap = {}; // key: "habitId_date_time" to avoid re-alerting inside the same minute

  function checkDueAlarms() {
    fetch('/api/v1/habits/reminders/active/', {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
      .then(function (r) {
        if (!r.ok) return null;
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.reminders || !Array.isArray(data.reminders)) return;

        var now = new Date();
        var currentHours = String(now.getHours()).padStart(2, '0');
        var currentMins = String(now.getMinutes()).padStart(2, '0');
        var currentTimeStr = currentHours + ':' + currentMins;
        var todayDateStr = data.server_date || now.toISOString().slice(0, 10);

        data.reminders.forEach(function (habit) {
          if (!habit.reminder_time) return;

          // Check if snoozed
          if (habit.snoozed_until) {
            var snoozeDate = new Date(habit.snoozed_until);
            if (snoozeDate > now) {
              return; // Still in snooze window
            }
          }

          var habitTime = habit.reminder_time.slice(0, 5); // "HH:MM"
          var alertKey = habit.id + '_' + todayDateStr + '_' + currentTimeStr;

          // If current minute matches the reminder time and not already fired for this minute
          if (currentTimeStr === habitTime && !alertedAlarmsMap[alertKey]) {
            alertedAlarmsMap[alertKey] = true;
            triggerHabitAlarm(habit);
          }
        });
      })
      .catch(function () {});
  }

  function triggerHabitAlarm(habit) {
    // 1. Play audio chime
    playAlarmChime();

    // 2. Show native system notification if permitted
    if ('Notification' in window && Notification.permission === 'granted') {
      try {
        var n = new Notification('⏰ HabitPulse: ' + habit.name, {
          body: 'Time to complete your habit! Keep your streak and earn ' + (habit.pixel_score || 2) + ' pixels.',
          icon: '/static/images/pwa_icon_192.png',
          tag: 'habit-alarm-' + habit.id,
          requireInteraction: true
        });
        n.onclick = function () {
          window.focus();
          window.location.href = '/habits/';
        };
      } catch (e) {
        console.log('[HabitAlarm] Notification error:', e);
      }
    }

    // 3. Show in-app floating banner
    showFloatingAlarm(habit);
  }

  // -------------------------------------------------------------------------
  // 5. Alarm Configuration Modal Handler
  // -------------------------------------------------------------------------
  function initAlarmModal() {
    var modal = document.getElementById('habit-alarm-modal');
    if (!modal) return;

    var habitIdInput = document.getElementById('modal-alarm-habit-id');
    var habitNameEl = document.getElementById('modal-alarm-habit-name');
    var enabledInput = document.getElementById('modal-alarm-enabled');
    var timeInput = document.getElementById('modal-alarm-time');
    var snoozeSelect = document.getElementById('modal-alarm-snooze');
    var form = document.getElementById('habit-alarm-form');
    var testBtn = document.getElementById('modal-alarm-test-btn');
    var calSyncBtn = document.getElementById('modal-alarm-calendar-btn');
    var closeBtn = document.getElementById('modal-alarm-close-btn');
    var cancelBtn = document.getElementById('modal-alarm-cancel-btn');

    function closeModal() {
      modal.style.display = 'none';
    }

    if (closeBtn) closeBtn.onclick = closeModal;
    if (cancelBtn) cancelBtn.onclick = closeModal;

    // Delegate click on any .habit-alarm-btn
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.habit-alarm-btn');
      if (!btn) return;
      e.preventDefault();

      var habitId = btn.getAttribute('data-habit-id');
      var habitName = btn.getAttribute('data-habit-name') || 'Habit';
      var enabled = btn.getAttribute('data-enabled') === '1';
      var timeVal = btn.getAttribute('data-time') || '';
      var snoozeVal = btn.getAttribute('data-snooze') || '0';

      habitIdInput.value = habitId;
      habitNameEl.textContent = habitName;
      enabledInput.checked = enabled;
      timeInput.value = timeVal || '08:00';
      snoozeSelect.value = snoozeVal;

      if (calSyncBtn) {
        calSyncBtn.href = '/habits/' + habitId + '/calendar.ics';
      }

      modal.style.display = 'flex';
      getAudioContext(); // Pre-warm audio context on user click
    });

    // Test Audio & Notification Button
    if (testBtn) {
      testBtn.onclick = function () {
        playAlarmChime();
        if ('Notification' in window) {
          if (Notification.permission === 'default') {
            Notification.requestPermission().then(function (perm) {
              if (perm === 'granted') {
                setupWebPushSubscription();
                new Notification('⏰ HabitPulse Alarm Test', {
                  body: 'Habit alarms and intimations are working perfectly on this device!',
                  icon: '/static/images/pwa_icon_192.png'
                });
              }
            });
          } else if (Notification.permission === 'granted') {
            new Notification('⏰ HabitPulse Alarm Test', {
              body: 'Habit alarms and intimations are working perfectly on this device!',
              icon: '/static/images/pwa_icon_192.png'
            });
          }
        }
      };
    }

    // Submit form via AJAX
    if (form) {
      form.onsubmit = function (e) {
        e.preventDefault();
        var habitId = habitIdInput.value;
        if (!habitId) return;

        var payload = {
          reminder_enabled: enabledInput.checked,
          reminder_time: timeInput.value,
          reminder_snooze_interval: parseInt(snoozeSelect.value, 10) || 0
        };

        fetch('/api/v1/habits/' + habitId + '/reminder/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
            'X-Requested-With': 'XMLHttpRequest'
          },
          body: JSON.stringify(payload)
        })
          .then(function (r) {
            if (!r.ok) {
              return r.text().then(function (text) {
                var msg = 'Server returned ' + r.status;
                try {
                  var errJson = JSON.parse(text);
                  if (errJson.error || errJson.detail) msg = errJson.error || errJson.detail;
                } catch (e) {}
                throw new Error(msg);
              });
            }
            return r.json();
          })
          .then(function (res) {
            closeModal();
            // Update button badge on page
            var btn = document.querySelector('.habit-alarm-btn[data-habit-id="' + habitId + '"]');
            if (btn) {
              btn.setAttribute('data-enabled', res.reminder_enabled ? '1' : '0');
              btn.setAttribute('data-time', res.reminder_time || '');
              btn.setAttribute('data-snooze', payload.reminder_snooze_interval);
              if (res.reminder_enabled && res.reminder_display && res.reminder_display !== 'Off') {
                btn.innerHTML = '<span style="color: #f59e0b;">⏰</span> ' + escapeHtml(res.reminder_display);
                btn.classList.add('has-alarm');
              } else {
                btn.innerHTML = '<span style="opacity: 0.65;">🔕</span> Set Alarm';
                btn.classList.remove('has-alarm');
              }
            }

            // Request notification permission if not yet decided
            if ('Notification' in window && Notification.permission === 'default' && payload.reminder_enabled) {
              Notification.requestPermission().then(function (perm) {
                if (perm === 'granted') setupWebPushSubscription();
              });
            }
          })
          .catch(function (err) {
            alert('Failed to update alarm: ' + err);
          });
      };
    }
  }

  // -------------------------------------------------------------------------
  // 6. Request Notification Permission Prompt Banner (PWA & Desktop)
  // -------------------------------------------------------------------------
  function checkNotificationBanner() {
    if (!('Notification' in window) || Notification.permission !== 'default') {
      return;
    }

    // Check if dismissed previously
    if (localStorage.getItem('habitpulse_alarm_banner_dismissed')) {
      return;
    }

    var banner = document.getElementById('habit-notification-permission-banner');
    if (banner) {
      banner.style.display = 'block';
      var enableBtn = document.getElementById('enable-push-notifications-btn');
      var dismissBtn = document.getElementById('dismiss-push-notifications-btn');

      if (enableBtn) {
        enableBtn.onclick = function () {
          Notification.requestPermission().then(function (permission) {
            banner.style.display = 'none';
            if (permission === 'granted') {
              setupWebPushSubscription();
              playAlarmChime();
            }
          });
        };
      }

      if (dismissBtn) {
        dismissBtn.onclick = function () {
          banner.style.display = 'none';
          localStorage.setItem('habitpulse_alarm_banner_dismissed', 'true');
        };
      }
    }
  }

  // -------------------------------------------------------------------------
  // 7. Initialization
  // -------------------------------------------------------------------------
  window.addEventListener('DOMContentLoaded', function () {
    initAlarmModal();
    checkNotificationBanner();
    setupWebPushSubscription();

    // Start background alarm polling every 30 seconds
    checkDueAlarms();
    setInterval(checkDueAlarms, 30000);
  });

  // Export helper functions to global window for external access
  window.HabitPulseAlarm = {
    playChime: playAlarmChime,
    checkDueAlarms: checkDueAlarms,
    setupPush: setupWebPushSubscription
  };
})();
