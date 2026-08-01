/* DeskStore: the demo's client-side state.
   Sample leads come from sample-leads.json (static, labelled Sample). Live-typed leads,
   done marks and approvals live in THIS visitor's localStorage only: a public demo must
   never show one visitor's enquiry to another, so nothing a visitor types leaves their
   browser except the single API call that drafts the reply. */
(function () {
  const LEADS_KEY = 'deskDemoLeads';
  const DONE_KEY = 'deskDemoDone';
  const APPROVE_KEY = 'deskDemoApprove';
  const ACCESS_KEY = 'deskDemoKey';

  /* the access key rides in on ?k=... once, then sticks for the browser */
  try {
    const k = new URLSearchParams(location.search).get('k');
    if (k) localStorage.setItem(ACCESS_KEY, k);
  } catch (e) {}

  function readJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return fallback;
      const parsed = JSON.parse(raw);
      return parsed == null ? fallback : parsed;
    } catch (e) { return fallback; }
  }
  function writeJSON(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }

  function apiHeaders() {
    const h = { 'Content-Type': 'application/json' };
    try {
      const k = localStorage.getItem(ACCESS_KEY);
      if (k) h['x-demo-key'] = k;
    } catch (e) {}
    return h;
  }

  /* ---- sample leads: hours-ago offsets become real timestamps at load ---- */
  let SAMPLE_CACHE = null;
  async function sampleLeads(now) {
    if (!SAMPLE_CACHE) {
      const res = await fetch('sample-leads.json');
      SAMPLE_CACHE = (await res.json()).leads;
    }
    return SAMPLE_CACHE.map(raw => {
      const lead = Object.assign({}, raw);
      lead.received = iso(new Date(now - raw.received_hours_ago * 3600000));
      lead.booked_for = raw.booked_in_hours != null ? iso(new Date(now.getTime() + raw.booked_in_hours * 3600000)) : null;
      lead.touches = (raw.touches || []).map(t => {
        const entry = { at: iso(new Date(now - t.hours_ago * 3600000)), type: t.type, note: t.note || '' };
        if (t.body) entry.body = t.body;
        return entry;
      });
      delete lead.received_hours_ago;
      delete lead.booked_in_hours;
      return lead;
    });
  }
  /* local-time ISO to the minute: these strings are re-parsed as local time everywhere */
  function iso(d) {
    const p = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  /* ---- live leads (this visitor only) ---- */
  function liveLeads() { return readJSON(LEADS_KEY, []); }
  function addLead(lead) {
    const leads = liveLeads();
    leads.push(lead);
    writeJSON(LEADS_KEY, leads);
  }
  function markDone(id, action) {
    const done = readJSON(DONE_KEY, {});
    done[id] = { at: iso(new Date()), action: action };
    writeJSON(DONE_KEY, done);
  }
  function recordApproval(id, type, body) {
    const approved = readJSON(APPROVE_KEY, {});
    (approved[id] = approved[id] || []).push({ at: iso(new Date()), type: type, body: body });
    writeJSON(APPROVE_KEY, approved);
  }

  /* ---- turning a brain card into a lead row (port of serve.py lead_from_card) ---- */
  const NAME_PATTERNS = [
    /[Mm]y [Nn]ame [Ii]s\s+((?:Mr|Ms|Mrs|Dr)\.?\s+)?([A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+)?)/,
    /[Tt]his [Ii]s\s+((?:Mr|Ms|Mrs|Dr)\.?\s+)?([A-Z][a-zA-Z'-]+)/,
    /(?:[Ii] am|[Ii]'m)\s+((?:Mr|Ms|Mrs|Dr)\.?\s+)?([A-Z][a-zA-Z'-]+)(?!\s+(?:looking|writing|interested|based|currently|planning|working))/,
    /(?:[Rr]egards|[Tt]hanks|[Tt]hank [Yy]ou|[Bb]est|[Cc]heers),?\s*\n+\s*()([A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+)?)\s*$/
  ];
  const EMAIL_PATTERN = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;

  function displayName(enquiry, card) {
    for (const p of NAME_PATTERNS) {
      const m = p.exec(enquiry);
      if (m) return ((m[1] || '') + ' ' + m[2]).trim();
    }
    let snippet = enquiry.split(/\s+/).join(' ');
    if (snippet.length > 26) {
      let cut = snippet.slice(0, 26);
      if (cut.includes(' ')) cut = cut.slice(0, cut.lastIndexOf(' '));
      snippet = cut.replace(/[,.;:]+$/, '') + '...';
    }
    return snippet ? '“' + snippet + '”' : 'Unnamed enquirer';
  }

  function leadFromCard(enquiry, card, responseSeconds, channel, guardrail) {
    const now = new Date();
    const emailMatch = EMAIL_PATTERN.exec(enquiry);
    const escalate = !!card.escalate;
    const bucket = String(card.bucket || 'unclear');
    let status = 'awaiting_reply';
    if (escalate) status = 'escalated';
    else if (bucket === 'not_an_enquiry') status = 'archived';
    const logRow = (card.log_row && typeof card.log_row === 'object') ? card.log_row : {};
    const touches = [];
    if (guardrail && guardrail.blocked && guardrail.kind === 'draft_block') {
      touches.push({
        at: iso(now), type: 'guardrail_block',
        note: (guardrail.hits || []).map(h => h.category + ': “' + h.match + '”').join('; '),
        body: guardrail.original_draft || ''
      });
    }
    if (card.draft) {
      touches.push({
        at: iso(now),
        type: escalate ? 'acknowledgment' : 'first_reply',
        note: String(logRow.next_action || '').slice(0, 120),
        body: String(card.draft || '')
      });
    }
    return {
      id: 'D-' + now.toISOString().slice(5, 19).replace(/[-T:]/g, ''),
      sample: false,
      channel: channel,
      phone: null,
      email: emailMatch ? emailMatch[0] : null,
      enquirer: displayName(enquiry, card),
      original_enquiry: enquiry,
      language: String(card.language || 'en'),
      bucket: bucket,
      stream: String(card.stream || 'none'),
      urgent: !!card.urgent,
      escalate: escalate,
      escalation_reasons: card.escalation_reasons || [],
      status: status,
      first_response_minutes: Math.max(1, Math.round(responseSeconds / 60)),
      received: iso(now),
      booked_for: null,
      touches: touches,
      summary: String(logRow.summary || enquiry.slice(0, 80)),
      next_action: String(logRow.next_action || '')
    };
  }

  /* ---- follow-up scheduling (port of serve.py next_followup) ---- */
  const CHASE_TYPES = ['chase_1', 'chase_2', 'final_chase'];
  function parseDt(v) {
    if (!v) return null;
    const d = new Date(v);
    return isNaN(d) ? null : d;
  }
  function lastTouchAt(lead) {
    const stamps = (lead.touches || []).map(t => parseDt(t.at)).filter(Boolean);
    const received = parseDt(lead.received) || new Date();
    return stamps.length ? new Date(Math.max.apply(null, stamps)) : received;
  }
  function nextFollowup(lead, now) {
    const status = String(lead.status || '');
    const touchTypes = (lead.touches || []).map(t => String(t.type));
    const last = lastTouchAt(lead);
    if (['escalated', 'archived', 'attended', 'closed'].includes(status)) return null;
    if (status === 'booked') {
      const bookedFor = parseDt(lead.booked_for);
      if (!bookedFor || touchTypes.includes('booking_reminder')) return null;
      return { type: 'booking_reminder', due: iso(new Date(bookedFor - 24 * 3600000)) };
    }
    if (status === 'no_show') {
      if (touchTypes.includes('no_show_rebook')) return null;
      return { type: 'no_show_rebook', due: iso(new Date(last.getTime() + 2 * 3600000)) };
    }
    if (status === 'nurture') return { type: 'nurture', due: iso(new Date(last.getTime() + 30 * 86400000)) };
    if (status === 'awaiting_reply') {
      const chases = touchTypes.filter(t => CHASE_TYPES.includes(t));
      if (chases.includes('final_chase')) return null;
      const delays = [['chase_1', 24 * 3600000], ['chase_2', 3 * 86400000], ['final_chase', 7 * 86400000]];
      const pick = delays[Math.min(chases.length, 2)];
      return { type: pick[0], due: iso(new Date(last.getTime() + pick[1])) };
    }
    return null;
  }

  /* ---- the merged view every page renders from ---- */
  async function allLeads(now) {
    const leads = (await sampleLeads(now)).concat(liveLeads());
    const done = readJSON(DONE_KEY, {});
    const approved = readJSON(APPROVE_KEY, {});
    leads.forEach(lead => {
      if (!Array.isArray(lead.touches)) lead.touches = [];
      (approved[String(lead.id)] || []).forEach(sent => {
        lead.touches.push({ at: sent.at, type: sent.type, note: 'approved by you, sent by the desk', body: sent.body || '' });
      });
      const doneEntry = done[String(lead.id)];
      if (doneEntry && doneEntry.at) {
        lead.done = true;
        lead.touches.push({ at: doneEntry.at, type: 'marked_done', action: doneEntry.action || '', note: '' });
      }
      let followup = nextFollowup(lead, now);
      if (doneEntry && doneEntry.at && followup && String(followup.due || '') <= doneEntry.at) followup = null;
      lead.followup = followup;
    });
    leads.sort((a, b) => String(a.received) < String(b.received) ? 1 : -1);
    return leads;
  }

  /* the lead subset the stateless follow-up endpoint needs */
  function followupPayload(lead) {
    return {
      original_enquiry: lead.original_enquiry,
      language: lead.language,
      bucket: lead.bucket,
      stream: lead.stream,
      escalate: lead.escalate,
      escalation_reasons: lead.escalation_reasons,
      status: lead.status,
      booked_for: lead.booked_for,
      touches: lead.touches,
      last_inbound_at: lead.received
    };
  }

  window.DeskStore = {
    apiHeaders: apiHeaders,
    allLeads: allLeads,
    addLead: addLead,
    markDone: markDone,
    recordApproval: recordApproval,
    leadFromCard: leadFromCard,
    followupPayload: followupPayload
  };
})();
