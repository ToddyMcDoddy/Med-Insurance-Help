(() => {
  'use strict';

  const app = document.getElementById('app');
  if (!app || document.getElementById('unsurance-a11y-announcement')) return;

  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const canDictate = window.isSecureContext && typeof Recognition === 'function';
  const preferenceKey = 'a11y-extra';
  const html = document.documentElement;
  const announcement = document.createElement('div');
  announcement.id = 'unsurance-a11y-announcement';
  announcement.className = 'ua11y-sr-only';
  announcement.setAttribute('role', 'status');
  announcement.setAttribute('aria-live', 'polite');
  announcement.setAttribute('aria-atomic', 'true');
  document.body.append(announcement);

  let speech = null;
  let voiceMessage = '';
  let colorblind = false;

  try {
    colorblind = localStorage.getItem(preferenceKey) === 'true';
  } catch {
    // The setting still works for this page when storage is blocked.
  }
  html.classList.toggle('ua11y-colorblind', colorblind);

  const speechErrors = {
    'not-allowed': 'Microphone access was denied. Allow it in your browser settings, then try again.',
    'service-not-allowed': 'Voice input is unavailable in this browser. You can type your question.',
    'audio-capture': 'The browser could not find a microphone. Check that one is connected.',
    'no-speech': 'No speech was detected. Try again when you are ready.',
    network: 'The browser speech service is unavailable. Try again or type your question.',
  };

  function updateVoiceControls() {
    const button = app.querySelector('.ua11y-mic');
    const message = app.querySelector('.ua11y-voice-status');
    if (!button || !message) return;

    button.setAttribute('aria-pressed', String(Boolean(speech)));
    button.setAttribute('aria-disabled', String(Boolean(speech?.stopping)));
    const micLabel = button.querySelector('.ua11y-mic-label'); const micText = speech ? 'Speaking…' : 'Speak'; if (micLabel) { if (micLabel.textContent !== micText) micLabel.textContent = micText; }
    if (message.textContent !== voiceMessage) message.textContent = voiceMessage;
  }

  function showVoiceMessage(message) {
    voiceMessage = message;
    if (announcement.textContent !== message) announcement.textContent = message;
    updateVoiceControls();
  }

  function finishDictation(session, errorMessage) {
    if (speech !== session) return;
    speech = null;
    const question = app.querySelector('#chat-form textarea#question');
    const transcript = session.transcript.trim();
    if (errorMessage || !question || !transcript) {
      showVoiceMessage(errorMessage || '');
      return;
    }

    const separator = question.value && !/\s$/.test(question.value) ? ' ' : '';
    question.value += separator + transcript;
    question.dispatchEvent(new Event('input', { bubbles: true }));
    showVoiceMessage('Voice input added. Review your question before sending.');
  }

  function toggleDictation() {
    if (speech) {
      const session = speech;
      if (session.stopping) return;
      session.stopping = true;
      showVoiceMessage('Finishing voice input…');
      try {
        session.recognition.stop();
      } catch {
        finishDictation(session, 'Voice input stopped. You can try again.');
        session.recognition.abort();
      }
      return;
    }

    let session;
    try {
      const recognition = new Recognition();
      session = { recognition, transcript: '', stopping: false };
      speech = session;
      recognition.lang = 'en-US';
      recognition.interimResults = false;
      recognition.continuous = false;
      recognition.onstart = () => {
        if (speech === session && !session.stopping) showVoiceMessage('Listening…');
      };
      recognition.onresult = (event) => {
        if (speech !== session) return;
        const segments = [];
        for (let index = 0; index < event.results.length; index += 1) {
          const result = event.results[index];
          if (result.isFinal) segments.push(result[0].transcript.trim());
        }
        session.transcript = segments.join(' ');
      };
      recognition.onerror = ({ error }) => {
        finishDictation(session, speechErrors[error] || 'Voice input ended. Try again or type your question.');
      };
      recognition.onend = () => finishDictation(session);
      showVoiceMessage('Starting microphone…');
      recognition.start();
    } catch {
      if (session) finishDictation(session, 'The browser could not start voice input. You can type your question.');
      else showVoiceMessage('The browser could not start voice input. You can type your question.');
    }
  }

  function attachMicrophone() {
    if (!canDictate) return;
    const question = app.querySelector('#chat-form textarea#question');
    const composer = question?.closest('.composer') || question?.form?.querySelector('.composer');
    if (!composer) {
      if (speech) {
        const { recognition } = speech;
        speech = null;
        recognition.abort();
      }
      if (voiceMessage) showVoiceMessage('');
      return;
    }

    if (!composer.querySelector('.ua11y-mic')) {
      const tools = document.createElement('div');
      tools.className = 'ua11y-voice';

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'ua11y-mic';
      const icon = document.createElement('span');
      icon.className = 'ua11y-mic-icon';
      icon.setAttribute('aria-hidden', 'true');
      const micText0 = document.createElement('span'); micText0.className = 'ua11y-mic-label'; micText0.textContent = 'Speak'; button.append(icon, micText0);
      button.setAttribute('aria-label', 'Speak your question');
      button.setAttribute('aria-describedby', 'unsurance-a11y-voice-help');
      button.addEventListener('click', toggleDictation);

      const help = document.createElement('span');
      help.id = 'unsurance-a11y-voice-help';
      help.className = 'ua11y-voice-help';
      help.textContent = "Your browser's speech service hears your voice.";

      const status = document.createElement('span');
      status.className = 'ua11y-voice-status';
      tools.append(button, help, status);
      composer.append(tools);
    }
    updateVoiceControls();
  }

  function attachSettings() {
    const grid = app.querySelector('.settings-grid');
    if (!grid || grid.querySelector('.ua11y-setting')) return;

    // Prefer the card that already contains the display accessibility options.
    const displayCard = Array.from(grid.children).find((card) => {
      const text = card.textContent.toLowerCase();
      return text.includes('larger text') && text.includes('higher contrast');
    });
    const row = document.createElement('label');
    row.className = 'toggle-row ua11y-setting';
    const label = document.createElement('span');
    const title = document.createElement('strong');
    title.textContent = 'Colorblind-friendly colors';
    const hint = document.createElement('small');
    hint.textContent = 'Switches status colors to a blue and orange palette that is easier to tell apart.';
    label.append(title, hint);
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = colorblind;
    checkbox.addEventListener('change', () => {
      colorblind = checkbox.checked;
      html.classList.toggle('ua11y-colorblind', colorblind);
      try {
        localStorage.setItem(preferenceKey, String(colorblind));
      } catch {
        announcement.textContent = 'Your browser could not save this setting for your next visit.';
      }
    });
    row.append(label, checkbox);
    const contrastRow = displayCard?.querySelector('#high-contrast')?.closest('.toggle-row');
    if (contrastRow) contrastRow.after(row);
    else (displayCard || grid).append(row);
  }

  const statusSelectors = [
    '.plan-pill', '.plan-status', '.status-pill', '.pill', '.flag',
    '.estimate-box', '.estimate-result', '.estimate-status',
  ].join(', ');

  const statuses = [
    { tokens: ['not-covered', 'uncovered', 'denied', 'excluded'], label: 'Not covered', tone: 'attention', text: /not covered|uncovered|denied|excluded/i },
    { tokens: ['out-of-network', 'oon'], label: 'Out of network', tone: 'attention', text: /out[ -]of[ -]network/i },
    { tokens: ['in-network'], label: 'In network', tone: 'positive', text: /in[ -]network/i },
    { tokens: ['unconfirmed', 'pending', 'draft'], label: 'Pending confirmation', tone: 'info', text: /unconfirmed|pending|draft|needs confirmation/i },
    { tokens: ['confirmed', 'verified'], label: 'Confirmed', tone: 'positive', text: /confirmed|verified/i },
    { tokens: ['covered'], label: 'Covered', tone: 'positive', text: /\bcovered\b/i },
    { tokens: ['high', 'critical', 'danger', 'error', 'bad'], label: 'Needs review', tone: 'attention', text: /high priority|critical|error|needs review/i },
    { tokens: ['warn', 'warning', 'caution', 'suspicious', 'medium'], label: 'Check this item', tone: 'attention', text: /warning|caution|check this|worth asking/i },
    { tokens: ['success', 'ok', 'good', 'positive', 'clear'], label: 'OK', tone: 'positive', text: /\bok\b|success|clear|no (flags|issues)/i },
    { tokens: ['low', 'info', 'neutral'], label: 'Information', tone: 'info', text: /information|low priority/i },
  ];

  function annotateStatuses() {
    for (const element of app.querySelectorAll(statusSelectors)) {
      const tokens = [element.dataset.status, element.dataset.severity, ...element.classList]
        .filter(Boolean)
        .map((token) => token.trim().toLowerCase().replace(/[\s_]+/g, '-'));
      const status = statuses.find(({ tokens: values }) => values.some((value) =>
        tokens.some((token) => token === value ||
          ['is-', 'status-', 'pill-', 'pill--', 'flag-', 'flag--', 'estimate-', 'estimate--']
            .some((prefix) => token === prefix + value))));
      const fallbackTone = element.classList.contains('flag') ? 'attention' : 'info';
      element.dataset.ua11yTone = status?.tone || fallbackTone;
      const badge = element.querySelector(':scope > .ua11y-status-label');
      const visibleText = Array.from(element.childNodes)
        .filter((child) => child !== badge && !child.matches?.('[hidden], [aria-hidden="true"], svg'))
        .map((child) => child.textContent)
        .join(' ').trim();
      const alternateLabel = element.getAttribute('aria-label') || element.getAttribute('title');
      let label = '';
      if (status && !status.text.test(visibleText)) {
        label = status.label;
      } else if (!visibleText && alternateLabel) {
        label = alternateLabel;
      }
      if (!label) {
        badge?.remove();
      } else if (badge) {
        if (badge.textContent !== label) badge.textContent = label;
      } else {
        const added = document.createElement('span');
        added.className = 'ua11y-status-label';
        added.textContent = label;
        element.append(added);
      }
    }
  }

  function enhance() {
    attachMicrophone();
    attachSettings();
    annotateStatuses();
  }

  const observer = new MutationObserver(enhance);
  observer.observe(app, { childList: true, subtree: true, characterData: true });
  enhance();
})();
