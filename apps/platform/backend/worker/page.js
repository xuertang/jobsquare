// Injected into every application page. Reads the form: finds fields, works
// out their labels and options, and reports current values. It never changes
// a value and never clicks anything; all writing is done by the Python side.
(() => {
  if (window.__copilot) return;

  const SKIP_INPUT = new Set(['hidden', 'submit', 'button', 'reset', 'image', 'password']);
  const TEXT_INPUT = { text: 'text', email: 'email', tel: 'tel', url: 'url',
                       number: 'number', search: 'text', date: 'date', '': 'text' };
  const PLACEHOLDER = /^(select|choose|please select|pick|--+|\u2014+|none selected)\b|^\s*$/i;

  const clean = (s) => (s || '').replace(/\s+/g, ' ')
    .replace(/(\s*(\*|\u2731|\(required\)|\(optional\)))+\s*$/i, '').trim();
  const text = (el) => clean(el ? el.textContent : '');

  // querySelectorAll that also walks open shadow roots (SmartRecruiters).
  function deepAll(root, selector, out = []) {
    for (const el of root.querySelectorAll('*')) {
      if (el.matches(selector)) out.push(el);
      if (el.shadowRoot) deepAll(el.shadowRoot, selector, out);
    }
    return out;
  }

  const parentOf = (el) => el.parentElement || (el.getRootNode() && el.getRootNode().host) || null;

  function visible(el) {
    if (!el || !el.isConnected) return false;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none';
  }

  // Custom radios and checkboxes hide the native input; the label is what shows.
  function shown(el) {
    if (visible(el)) return true;
    const label = optionLabelEl(el);
    return visible(label) || visible(el.parentElement);
  }

  function byIds(el, attr) {
    const ids = (el.getAttribute(attr) || '').split(/\s+/).filter(Boolean);
    const root = el.getRootNode();
    return clean(ids.map((id) => {
      const ref = root.getElementById ? root.getElementById(id) : document.getElementById(id);
      return ref ? ref.textContent : '';
    }).join(' '));
  }

  function labelFor(el) {
    if (!el.id) return null;
    const root = el.getRootNode();
    try { return root.querySelector(`label[for="${CSS.escape(el.id)}"]`); } catch (e) { return null; }
  }

  function optionLabelEl(el) {
    return labelFor(el) || el.closest('label');
  }

  function optionLabel(el) {
    const label = optionLabelEl(el);
    return text(label) || clean(el.getAttribute('aria-label')) || byIds(el, 'aria-labelledby')
      || clean(el.nextSibling && el.nextSibling.textContent) || clean(el.value);
  }

  const LABELISH = ':scope > label, :scope > legend, :scope > [class*="label" i], '
    + ':scope > [class*="question" i], :scope > [class*="title" i]';

  // Label of a single control: explicit associations first, then the nearest
  // enclosing field container that carries a label-like child.
  function labelOf(el) {
    let t = byIds(el, 'aria-labelledby');
    if (t) return t;
    if (el.type === 'file') {
      // The input's own label is the "Attach" button; the question is on
      // the enclosing upload group (Greenhouse).
      const group = el.closest('[role="group"], fieldset');
      if (group) {
        t = byIds(group, 'aria-labelledby') || clean(group.getAttribute('aria-label'))
          || text(group.querySelector(':scope > legend'));
        if (t) return t;
      }
    }
    t = text(labelFor(el));
    if (t) return t;
    const wrap = el.closest('label');
    if (wrap) {
      // Lever wraps the whole field in a <label>: the question is the
      // label-like child, the rest is upload status and helper text.
      for (const c of wrap.querySelectorAll('[class*="label" i], [class*="question" i], [class*="title" i]')) {
        if (c.contains(el) || c.querySelector('input, select, textarea')) continue;
        t = text(c);
        if (t) return t;
      }
      const copy = wrap.cloneNode(true);
      copy.querySelectorAll('input, select, textarea, button').forEach((n) => n.remove());
      t = text(copy);
      if (t) return t;
    }
    t = clean(el.getAttribute('aria-label'));
    if (t) return t;
    let node = el;
    for (let hop = 0; hop < 6 && node; hop++) {
      const parent = parentOf(node);
      if (!parent) break;
      if (parent !== node.parentElement) {          // crossed a shadow boundary
        t = clean(parent.getAttribute('label') || parent.getAttribute('aria-label'));
        if (t) return t;
      }
      for (const c of parent.querySelectorAll(LABELISH)) {
        if (c === node || c.contains(el)) continue;
        if (c.querySelector('input, select, textarea')) continue;
        t = text(c);
        if (t) return t;
      }
      node = parent;
    }
    return clean(el.getAttribute('placeholder')) || clean(el.getAttribute('title'));
  }

  // Question of a radio or checkbox group: the legend or label of the
  // smallest container that holds every option, skipping the option labels.
  function groupLabel(inputs) {
    let anc = inputs[0].parentElement;
    while (anc && !inputs.every((i) => anc.contains(i))) anc = anc.parentElement;
    const optionEls = inputs.map(optionLabelEl).filter(Boolean);
    const isOption = (c) => optionEls.some((o) => o === c || o.contains(c) || c.contains(o));
    for (let hop = 0; anc && hop < 5; hop++, anc = anc.parentElement) {
      let t = byIds(anc, 'aria-labelledby') || clean(anc.getAttribute('aria-label'));
      if (t) return t;
      const picks = anc.querySelectorAll(
        'legend, label, [class*="label" i], [class*="question" i], [class*="title" i], h2, h3, h4, h5, p');
      for (const c of picks) {
        if (c.querySelector('input, select, textarea') || isOption(c)) continue;
        t = text(c);
        if (t) return t;
      }
    }
    return '';
  }

  const isRequired = (el) => el.required || el.getAttribute('aria-required') === 'true'
    || /\*\s*$/.test((optionLabelEl(el) || {}).textContent || '');

  const isCombobox = (el) => el.getAttribute('role') === 'combobox'
    || el.hasAttribute('aria-autocomplete') || el.getAttribute('aria-haspopup') === 'listbox';

  function comboValue(el) {
    const control = el.closest('[class*="control"]')
      || el.closest('[class*="select"], [class*="combobox"]');
    if (control) {
      const multi = [...control.querySelectorAll('[class*="multi-value__label"], [class*="multiValue"] [class*="label"]')];
      if (multi.length) return multi.map(text).join('; ');
      const single = control.querySelector('[class*="single-value"], [class*="singleValue"]');
      if (single) return text(single);
    }
    return clean(el.value != null ? el.value : el.textContent);
  }

  function slug(s) {
    return (s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 48);
  }

  function extract(rootSelector) {
    const root = (rootSelector && document.querySelector(rootSelector)) || document.body;
    const fields = [];
    const used = new Map();
    const key = (kind, el, label) => {
      const base = `${kind}:${el.getAttribute('name') || el.id || slug(label) || 'field'}`;
      const n = (used.get(base) || 0) + 1;
      used.set(base, n);
      return n === 1 ? base : `${base}#${n}`;
    };
    const add = (el, f) => {
      el.setAttribute('data-copilot-key', f.key);
      fields.push({ name: el.getAttribute('name') || '', id: el.id || '',
                    autocomplete: el.getAttribute('autocomplete') || '',
                    required: isRequired(el), options: [], value: '', ...f });
    };

    // Yes/No button pairs (Ashby renders boolean questions this way, with a
    // hidden checkbox beside the buttons that mirrors the choice).
    const pairs = new Map();
    for (const b of deepAll(root, 'button')) {
      if ((b.getAttribute('type') || '').toLowerCase() === 'submit') continue;
      if (!/^(yes|no)$/i.test(text(b)) || !visible(b)) continue;
      const parent = b.parentElement;
      if (!pairs.has(parent)) pairs.set(parent, []);
      pairs.get(parent).push(b);
    }
    for (const [parent, buttons] of [...pairs]) if (buttons.length !== 2) pairs.delete(parent);
    const inPair = (el) => [...pairs.keys()].some((parent) => parent.contains(el));

    const radios = new Map();
    const checks = new Map();
    for (const el of deepAll(root, 'input, select, textarea, [role="combobox"]:not(input), button[aria-haspopup="listbox"]')) {
      const tag = el.tagName.toLowerCase();
      const type = (el.getAttribute('type') || '').toLowerCase();
      if (el.disabled || el.closest('[aria-hidden="true"]') && type !== 'file') continue;

      if (tag === 'input' && type === 'file') {
        const label = labelOf(el);
        // "Autofill from resume" parses a file and overwrites the form: skip it.
        const near = text(el.closest('[class*="autofill" i]')) || label;
        if (/auto-?fill/i.test(near)) continue;
        add(el, { key: key('file', el, label), label, type: 'file',
                  value: el.files && el.files[0] ? el.files[0].name : '' });
        continue;
      }
      if (tag === 'input' && type === 'radio') {
        if (!shown(el)) continue;
        const group = el.name ? `n:${el.name}` : `c:${fields.length}:${radios.size}`;
        if (!radios.has(group)) radios.set(group, []);
        radios.get(group).push(el);
        continue;
      }
      if (tag === 'input' && type === 'checkbox') {
        if (inPair(el) || !shown(el)) continue;
        const group = el.name ? `n:${el.name}` : `solo:${checks.size}`;
        if (!checks.has(group)) checks.set(group, []);
        checks.get(group).push(el);
        continue;
      }
      if (tag === 'input' && SKIP_INPUT.has(type)) continue;
      if (!visible(el) && !(isCombobox(el) && visible(el.closest('[class*="control"]')))) continue;

      const label = labelOf(el);
      if (tag === 'select') {
        const options = [...el.options].map((o) => clean(o.textContent))
          .filter((t) => !PLACEHOLDER.test(t));
        const picked = el.selectedOptions[0] ? clean(el.selectedOptions[0].textContent) : '';
        add(el, { key: key('select', el, label), label, type: 'select', options,
                  value: PLACEHOLDER.test(picked) ? '' : picked });
      } else if (tag === 'textarea') {
        add(el, { key: key('textarea', el, label), label, type: 'textarea', value: el.value });
      } else if (tag !== 'input' || isCombobox(el)) {
        add(el, { key: key('combobox', el, label), label, type: 'combobox',
                  value: comboValue(el) });
      } else if (type in TEXT_INPUT) {
        add(el, { key: key(TEXT_INPUT[type], el, label), label, type: TEXT_INPUT[type],
                  value: el.value });
      }
    }

    for (const inputs of radios.values()) {
      const label = groupLabel(inputs);
      const k = key('radio', inputs[0], label);
      const options = inputs.map((i) => {
        const o = optionLabel(i);
        i.setAttribute('data-copilot-group', k);
        i.setAttribute('data-copilot-opt', o);
        return o;
      });
      const on = inputs.find((i) => i.checked);
      add(inputs[0], { key: k, label, type: 'radio', options, value: on ? optionLabel(on) : '',
                       required: inputs.some(isRequired) });
    }
    for (const inputs of checks.values()) {
      if (inputs.length === 1) {
        const el = inputs[0];
        const label = text(optionLabelEl(el)) || clean(el.getAttribute('aria-label'))
          || labelOf(el) || optionLabel(el);
        add(el, { key: key('checkbox', el, label), label, type: 'checkbox',
                  value: el.checked ? 'yes' : '' });
        continue;
      }
      const label = groupLabel(inputs);
      const k = key('checkboxes', inputs[0], label);
      const options = inputs.map((i) => {
        const o = optionLabel(i);
        i.setAttribute('data-copilot-group', k);
        i.setAttribute('data-copilot-opt', o);
        return o;
      });
      add(inputs[0], { key: k, label, type: 'checkboxes', options,
                       value: inputs.filter((i) => i.checked).map(optionLabel).join('; ') });
    }

    for (const [parent, buttons] of pairs) {
      const label = labelOf(parent);
      const k = key('radio', parent, label);
      buttons.forEach((b) => {
        b.setAttribute('data-copilot-group', k);
        b.setAttribute('data-copilot-opt', text(b));
      });
      const on = buttons.find((b) => b.getAttribute('aria-pressed') === 'true'
        || b.getAttribute('aria-checked') === 'true' || /(^|[_\s-])(active|selected)/i.test(b.className));
      add(parent, { key: k, label, type: 'radio', options: buttons.map(text),
                    value: on ? text(on) : '', widget: 'buttons' });
    }
    return fields;
  }

  function values(rootSelector) {
    const out = {};
    for (const f of extract(rootSelector)) out[f.key] = f.value || '';
    return out;
  }

  // Remember the form as it stood when the user pressed submit, so the final
  // answers survive the navigation to the confirmation page.
  let rootSel = null;
  const remember = () => {
    try { sessionStorage.setItem('__copilot_final', JSON.stringify(values(rootSel))); } catch (e) { /* ignore */ }
  };
  document.addEventListener('submit', (e) => {
    if (window.__copilotFilling) {          // never during an automated fill
      e.preventDefault();
      e.stopImmediatePropagation();
      window.__copilotBlockedSubmits = (window.__copilotBlockedSubmits || 0) + 1;
      return;
    }
    remember();
  }, true);
  document.addEventListener('click', (e) => {
    const b = e.target && e.target.closest ? e.target.closest('button, input[type="submit"]') : null;
    if (b && !window.__copilotFilling && /submit|apply|send/i.test(b.textContent || b.value || '')) remember();
  }, true);

  window.__copilot = {
    extract: (sel) => { rootSel = sel || null; return extract(sel); },
    values,
    final: () => { try { return JSON.parse(sessionStorage.getItem('__copilot_final') || 'null'); } catch (e) { return null; } },
  };
})();
