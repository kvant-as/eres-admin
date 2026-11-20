(function () {
  'use strict';

  var EA = window.EA || {};
  var root = document.documentElement;
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (e) {
      return null;
    }
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  document.querySelectorAll('[data-ea-theme]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      if (!reduceMotion) {
        root.classList.add('ea-theme-anim');
        clearTimeout(btn._eaThemeTimer);
        btn._eaThemeTimer = setTimeout(function () { root.classList.remove('ea-theme-anim'); }, 360);
      }
      root.setAttribute('data-theme', next);
      store(EA.themeKey || 'eres-admin-theme', next);
    });
  });

  if (!reduceMotion) {
    var risers = Array.prototype.filter.call(
      document.querySelectorAll('.ea-content .ea-stat, .ea-content .ea-card, .ea-content > .ea-alert'),
      function (node) { return !node.parentElement.closest('.ea-card'); }
    );
    risers.forEach(function (node, i) {
      node.style.animationDelay = Math.min(i, 10) * 45 + 'ms';
      node.classList.add('ea-rise');
      node.addEventListener('animationend', function done() {
        node.classList.remove('ea-rise');
        node.style.animationDelay = '';
        node.removeEventListener('animationend', done);
      });
    });

    document.querySelectorAll('.ea-stat-value').forEach(function (el) {
      var text = el.textContent.trim();
      if (!/^\d+$/.test(text)) return;
      var target = parseInt(text, 10);
      if (target < 2) return;
      var start = null;
      var duration = 900;
      el.textContent = '0';
      function step(ts) {
        if (start === null) start = ts;
        var t = Math.min(1, (ts - start) / duration);
        var eased = 1 - Math.pow(1 - t, 3);
        el.textContent = String(Math.round(target * eased));
        if (t < 1) requestAnimationFrame(step);
      }
      setTimeout(function () { requestAnimationFrame(step); }, 120);
    });

    var fills = document.querySelectorAll('.ea-bar-fill');
    fills.forEach(function (bar) {
      bar.dataset.eaWidth = bar.style.width;
      bar.style.width = '0';
    });
    if (fills.length) {
      setTimeout(function () {
        fills.forEach(function (bar, i) {
          bar.style.transitionDelay = Math.min(i, 8) * 50 + 'ms';
          bar.style.width = bar.dataset.eaWidth;
        });
      }, 250);
    }
  }

  function setSide(open) {
    root.classList.toggle('ea-side-open', open);
  }
  document.querySelectorAll('[data-ea-side-open]').forEach(function (b) {
    b.addEventListener('click', function () { setSide(true); });
  });
  document.querySelectorAll('[data-ea-side-close]').forEach(function (b) {
    b.addEventListener('click', function () { setSide(false); });
  });

  var collapsed = {};
  try { collapsed = JSON.parse(store('eres-admin-groups') || '{}'); } catch (e) { collapsed = {}; }
  document.querySelectorAll('[data-ea-group]').forEach(function (group) {
    var name = group.getAttribute('data-ea-group');
    var head = group.querySelector('.ea-nav-group-head');
    var hasActive = !!group.querySelector('.is-active');
    function apply(isCollapsed) {
      group.classList.toggle('is-collapsed', isCollapsed);
      head.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
    }
    apply(!!collapsed[name] && !hasActive);
    head.addEventListener('click', function () {
      var now = !group.classList.contains('is-collapsed');
      apply(now);
      if (now) collapsed[name] = 1; else delete collapsed[name];
      store('eres-admin-groups', JSON.stringify(collapsed));
    });
  });
  var activeItem = document.querySelector('.ea-nav-item.is-active');
  if (activeItem && activeItem.scrollIntoView) activeItem.scrollIntoView({ block: 'nearest' });

  function dismissToast(toast) {
    if (!toast || toast.classList.contains('is-leaving')) return;
    toast.classList.add('is-leaving');
    setTimeout(function () { toast.remove(); }, 220);
  }
  function wireToast(toast) {
    toast.querySelector('.ea-toast-close').addEventListener('click', function () { dismissToast(toast); });
    var error = toast.classList.contains('ea-toast--error');
    setTimeout(function () { dismissToast(toast); }, error ? 9000 : 4500);
  }
  document.querySelectorAll('.ea-toast').forEach(wireToast);

  EA.toast = function (text, kind) {
    var box = document.querySelector('.ea-toasts');
    if (!box) return;
    var toast = el('div', 'ea-toast ea-toast--' + (kind || 'info'));
    toast.setAttribute('role', 'status');
    toast.appendChild(el('span', 'ea-toast-text', text));
    var close = el('button', 'ea-toast-close', '×');
    close.type = 'button';
    close.setAttribute('aria-label', 'Закрыть');
    toast.appendChild(close);
    box.appendChild(toast);
    wireToast(toast);
  };

  var confirmDialog = document.getElementById('eaConfirm');
  EA.confirm = function (text, okLabel) {
    return new Promise(function (resolve) {
      if (!confirmDialog || typeof confirmDialog.showModal !== 'function') {
        resolve(window.confirm(text));
        return;
      }
      confirmDialog.querySelector('[data-ea-confirm-text]').textContent = text;
      confirmDialog.querySelector('[data-ea-confirm-ok]').textContent = okLabel || 'Подтвердить';
      confirmDialog.returnValue = '';
      confirmDialog.addEventListener('close', function onClose() {
        confirmDialog.removeEventListener('close', onClose);
        resolve(confirmDialog.returnValue === 'ok');
      });
      confirmDialog.showModal();
    });
  };

  document.addEventListener('submit', function (e) {
    var form = e.target;
    var message = form.getAttribute('data-confirm');
    if (!message || form.dataset.eaConfirmed) return;
    e.preventDefault();
    var submitter = e.submitter;
    EA.confirm(message, submitter && submitter.textContent.trim()).then(function (ok) {
      if (!ok) return;
      form.dataset.eaConfirmed = '1';
      if (form.requestSubmit) form.requestSubmit(submitter); else form.submit();
    });
  }, true);

  var palette = document.getElementById('eaPalette');
  var paletteInput = palette && palette.querySelector('[data-ea-palette-input]');
  var paletteList = palette && palette.querySelector('[data-ea-palette-list]');
  var paletteItems = [];
  try { paletteItems = JSON.parse(document.getElementById('eaPaletteData').textContent); } catch (e) { paletteItems = []; }
  var paletteIndex = 0;

  function paletteMatches() {
    var term = (paletteInput.value || '').trim().toLowerCase();
    if (!term) return paletteItems;
    return paletteItems.filter(function (item) {
      return (item.label + ' ' + item.group).toLowerCase().indexOf(term) !== -1;
    });
  }
  function renderPalette() {
    var items = paletteMatches();
    paletteIndex = Math.min(paletteIndex, Math.max(items.length - 1, 0));
    paletteList.innerHTML = '';
    if (!items.length) {
      paletteList.appendChild(el('li', 'ea-palette-empty', 'Такого раздела нет'));
      return;
    }
    items.forEach(function (item, i) {
      var li = el('li', 'ea-palette-item' + (i === paletteIndex ? ' is-active' : ''));
      li.setAttribute('role', 'option');
      var a = el('a');
      a.href = item.url;
      a.appendChild(el('span', '', item.label));
      if (item.group) a.appendChild(el('small', '', item.group));
      li.appendChild(a);
      li.addEventListener('mousemove', function () {
        if (paletteIndex === i) return;
        paletteIndex = i;
        renderPalette();
      });
      paletteList.appendChild(li);
    });
  }
  function openPalette() {
    if (!palette || typeof palette.showModal !== 'function') return;
    paletteInput.value = '';
    paletteIndex = 0;
    renderPalette();
    palette.showModal();
    paletteInput.focus();
  }
  if (palette) {
    paletteInput.addEventListener('input', function () { paletteIndex = 0; renderPalette(); });
    paletteInput.addEventListener('keydown', function (e) {
      var items = paletteMatches();
      if (e.key === 'ArrowDown') { e.preventDefault(); paletteIndex = (paletteIndex + 1) % Math.max(items.length, 1); renderPalette(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); paletteIndex = (paletteIndex - 1 + items.length) % Math.max(items.length, 1); renderPalette(); }
      else if (e.key === 'Enter' && items[paletteIndex]) { e.preventDefault(); window.location.href = items[paletteIndex].url; }
    });
    palette.addEventListener('click', function (e) { if (e.target === palette) palette.close(); });
    document.querySelectorAll('[data-ea-palette-open]').forEach(function (b) { b.addEventListener('click', openPalette); });
  }

  var form = document.querySelector('[data-ea-form]');
  var dirty = false;
  function markDirty() {
    if (dirty) return;
    dirty = true;
    var note = document.querySelector('[data-ea-dirty]');
    if (note) note.hidden = false;
  }
  if (form) {
    form.addEventListener('input', markDirty);
    form.addEventListener('change', markDirty);
    form.addEventListener('submit', function () { dirty = false; });
    window.addEventListener('beforeunload', function (e) {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = '';
    });
    var firstError = form.querySelector('.has-error .ea-input');
    if (firstError) firstError.focus();
  }

  document.addEventListener('keydown', function (e) {
    var mod = e.ctrlKey || e.metaKey;
    if (mod && (e.key === 'k' || e.key === 'K' || e.code === 'KeyK')) {
      e.preventDefault();
      openPalette();
    } else if (mod && (e.key === 's' || e.key === 'S' || e.code === 'KeyS') && form) {
      e.preventDefault();
      if (form.requestSubmit) form.requestSubmit(); else form.submit();
    } else if (e.key === 'Escape') {
      setSide(false);
    }
  });

  document.querySelectorAll('[data-ea-password-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = btn.parentElement.querySelector('input');
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.setAttribute('aria-label', show ? 'Скрыть пароль' : 'Показать пароль');
    });
  });

  document.querySelectorAll('[data-ea-file]').forEach(function (box) {
    var input = box.querySelector('input[type="file"]');
    var name = box.querySelector('[data-ea-file-name]');
    var preview = box.querySelector('[data-ea-file-preview]');
    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (!file) return;
      name.textContent = file.name;
      if (file.type && file.type.indexOf('image/') === 0) {
        var img = document.createElement('img');
        img.alt = '';
        img.src = URL.createObjectURL(file);
        preview.innerHTML = '';
        preview.appendChild(img);
      }
    });
  });

  document.querySelectorAll('[data-ea-combo]').forEach(function (box) {
    var target = box.getAttribute('data-ea-combo');
    var input = box.querySelector('[data-ea-combo-input]');
    var hidden = box.querySelector('input[type="hidden"]');
    var list = box.querySelector('[data-ea-combo-list]');
    var timer = null;
    var items = [];
    var active = -1;
    var lastTerm = null;

    function close() { list.classList.remove('is-open'); active = -1; }
    function choose(item) {
      hidden.value = item.id;
      input.value = item.label;
      close();
      markDirty();
    }
    function render() {
      list.innerHTML = '';
      if (!items.length) {
        list.appendChild(el('div', 'ea-combo-empty', 'Ничего не найдено'));
      }
      items.forEach(function (item, i) {
        var row = el('div', 'ea-combo-item' + (i === active ? ' is-active' : ''), item.label);
        row.setAttribute('role', 'option');
        row.addEventListener('mousedown', function (e) { e.preventDefault(); choose(item); });
        list.appendChild(row);
      });
      list.classList.add('is-open');
    }
    function search(term) {
      if (!target || term === lastTerm) { if (items.length || lastTerm !== null) render(); return; }
      lastTerm = term;
      fetch(EA.fkSearchUrl + '?target=' + encodeURIComponent(target) + '&q=' + encodeURIComponent(term), { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (data) { items = data || []; active = items.length ? 0 : -1; render(); })
        .catch(close);
    }
    input.addEventListener('input', function () {
      hidden.value = '';
      var term = input.value.trim();
      clearTimeout(timer);
      if (term.length < 2) { close(); return; }
      timer = setTimeout(function () { search(term); }, 220);
    });
    input.addEventListener('keydown', function (e) {
      if (!list.classList.contains('is-open')) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(active + 1, items.length - 1); render(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(active - 1, 0); render(); }
      else if (e.key === 'Enter' && items[active]) { e.preventDefault(); choose(items[active]); }
      else if (e.key === 'Escape') { e.stopPropagation(); close(); }
    });
    input.addEventListener('blur', function () { setTimeout(close, 120); });
  });

  document.querySelectorAll('[data-ea-autosubmit]').forEach(function (f) {
    f.querySelectorAll('select').forEach(function (s) {
      s.addEventListener('change', function () {
        var page = f.querySelector('input[name="page"]');
        if (page) page.remove();
        f.submit();
      });
    });
  });

  document.querySelectorAll('tr[data-ea-href]').forEach(function (row) {
    row.addEventListener('click', function (e) {
      if (e.target.closest('a, button, input, label, select, details')) return;
      if (window.getSelection && String(window.getSelection()).length) return;
      if (e.ctrlKey || e.metaKey) window.open(row.getAttribute('data-ea-href'), '_blank');
      else window.location.href = row.getAttribute('data-ea-href');
    });
  });

  document.querySelectorAll('form.ea-bulk[id]').forEach(function (bulk) {
    var boxes = Array.prototype.slice.call(document.querySelectorAll('input[type="checkbox"][form="' + bulk.id + '"]'));
    var all = document.querySelector('[data-ea-check-all]');
    var count = bulk.querySelector('[data-ea-bulk-count]');
    function visible(b) {
      var tr = b.closest('tr');
      return !tr || !tr.hidden;
    }
    function sync() {
      var n = 0;
      var used = 0;
      boxes.forEach(function (b) {
        if (b.checked) {
          n += 1;
          if (b.getAttribute('data-in-use') === '1') used += 1;
        }
        var tr = b.closest('tr');
        if (tr) tr.classList.toggle('is-selected', b.checked);
      });
      bulk.hidden = n === 0;
      count.textContent = 'Выбрано: ' + n + (used ? ', из них привязаны к записям: ' + used : '');
      if (all) {
        var vis = boxes.filter(visible);
        var on = vis.filter(function (b) { return b.checked; }).length;
        all.checked = on > 0 && on === vis.length;
        all.indeterminate = on > 0 && on < vis.length;
      }
    }
    bulk._eaSync = sync;
    boxes.forEach(function (b) { b.addEventListener('change', sync); });
    if (all) all.addEventListener('change', function () {
      boxes.forEach(function (b) { if (visible(b)) b.checked = all.checked; });
      sync();
    });
    bulk.querySelector('[data-ea-bulk-clear]').addEventListener('click', function () {
      boxes.forEach(function (b) { b.checked = false; });
      sync();
    });
  });

  document.querySelectorAll('[data-ea-dialog-open]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var dlg = document.getElementById(btn.getAttribute('data-ea-dialog-open'));
      if (!dlg || typeof dlg.showModal !== 'function') return;
      var form = dlg.querySelector('form');
      if (form) form.reset();
      dlg.showModal();
      var input = dlg.querySelector('input:not([type="hidden"])');
      if (input) input.focus();
    });
  });
  document.querySelectorAll('dialog [data-ea-dialog-close]').forEach(function (btn) {
    btn.addEventListener('click', function () { btn.closest('dialog').close(); });
  });

  var renameDlg = document.getElementById('eaRename');
  document.querySelectorAll('[data-ea-rename]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!renameDlg) return;
      renameDlg.querySelector('input[name="path"]').value = btn.getAttribute('data-ea-rename');
      var input = renameDlg.querySelector('input[name="name"]');
      var name = btn.getAttribute('data-name') || '';
      input.value = name;
      renameDlg.showModal();
      input.focus();
      var dot = name.lastIndexOf('.');
      input.setSelectionRange(0, dot > 0 ? dot : name.length);
    });
  });

  var replaceForm = document.getElementById('eaReplaceForm');
  document.querySelectorAll('[data-ea-replace]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!replaceForm) return;
      replaceForm.querySelector('input[name="path"]').value = btn.getAttribute('data-ea-replace');
      var input = replaceForm.querySelector('input[type="file"]');
      input.value = '';
      input.onchange = function () {
        if (!input.files || !input.files[0]) return;
        EA.confirm('Заменить содержимое файла на «' + input.files[0].name + '»? Имя файла и привязка к записи сохранятся.', 'Заменить')
          .then(function (ok) { if (ok) replaceForm.submit(); });
      };
      input.click();
    });
  });

  var uploadForm = document.getElementById('eaUploadForm');
  if (uploadForm) {
    var uploadInput = uploadForm.querySelector('[data-ea-upload-input]');
    uploadInput.addEventListener('change', function () {
      if (uploadInput.files && uploadInput.files.length) {
        EA.toast('Загружаем файлов: ' + uploadInput.files.length, 'info');
        uploadForm.submit();
      }
    });
    document.querySelectorAll('[data-ea-upload-pick]').forEach(function (b) {
      b.addEventListener('click', function () { uploadInput.click(); });
    });
    var zone = document.querySelector('[data-ea-dropzone]');
    if (zone) {
      var depth = 0;
      zone.addEventListener('dragenter', function (e) {
        if (!e.dataTransfer || Array.prototype.indexOf.call(e.dataTransfer.types, 'Files') === -1) return;
        e.preventDefault();
        depth += 1;
        zone.classList.add('is-dragover');
      });
      zone.addEventListener('dragover', function (e) {
        if (zone.classList.contains('is-dragover')) e.preventDefault();
      });
      zone.addEventListener('dragleave', function () {
        depth = Math.max(0, depth - 1);
        if (!depth) zone.classList.remove('is-dragover');
      });
      zone.addEventListener('drop', function (e) {
        e.preventDefault();
        depth = 0;
        zone.classList.remove('is-dragover');
        if (!e.dataTransfer || !e.dataTransfer.files.length) return;
        uploadInput.files = e.dataTransfer.files;
        EA.toast('Загружаем файлов: ' + e.dataTransfer.files.length, 'info');
        uploadForm.submit();
      });
    }
  }

  var fileFilter = document.querySelector('[data-ea-files-filter]');
  var usageFilter = document.querySelector('[data-ea-files-usage]');
  function filterFiles() {
    var term = fileFilter ? fileFilter.value.trim().toLowerCase() : '';
    var usage = usageFilter ? usageFilter.value : '';
    var shown = 0;
    document.querySelectorAll('tr[data-ea-file-row]').forEach(function (tr) {
      var ok = !term || tr.getAttribute('data-name').indexOf(term) !== -1;
      if (ok && usage) {
        if (tr.getAttribute('data-dir') === '1') ok = false;
        else ok = usage === 'used' ? tr.getAttribute('data-used') === '1' : tr.getAttribute('data-used') !== '1';
      }
      tr.hidden = !ok;
      if (ok) shown += 1;
    });
    var none = document.querySelector('.ea-files-nomatch');
    if (none) none.hidden = shown > 0 || (!term && !usage);
    var bulkFiles = document.getElementById('eaFilesBulk');
    if (bulkFiles && bulkFiles._eaSync) bulkFiles._eaSync();
  }
  if (fileFilter) fileFilter.addEventListener('input', filterFiles);
  if (usageFilter) usageFilter.addEventListener('change', filterFiles);

  document.querySelectorAll('[data-ea-download]').forEach(function (a) {
    a.addEventListener('click', function () {
      EA.toast('Готовим архив базы. Скачивание начнётся автоматически через несколько секунд.', 'info');
    });
  });

  var status = document.querySelector('[data-ea-action-status]');
  function showStatus(text, ok) {
    if (!status) return;
    status.hidden = false;
    status.textContent = text;
    status.className = 'ea-action-status ' + (ok ? 'is-ok' : 'is-bad');
  }
  function runAction(btn, req) {
    var label = btn.querySelector('span');
    var original = label ? label.textContent : '';
    btn.disabled = true;
    if (label) label.textContent = 'Выполняется…';
    fetch(req.url, {
      method: req.method || 'POST',
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf },
      body: req.body
    })
      .then(function (r) {
        return r.json().catch(function () { return { success: r.ok }; }).then(function (d) { return { ok: r.ok, d: d || {} }; });
      })
      .then(function (res) {
        var ok = res.ok && res.d.success !== false;
        showStatus(res.d.message || (ok ? 'Готово' : 'Не удалось выполнить действие'), ok);
      })
      .catch(function () { showStatus('Нет связи с сервером. Повторите позже.', false); })
      .finally(function () {
        btn.disabled = false;
        if (label) label.textContent = original;
      });
  }
  function confirmThen(btn, fn) {
    var message = btn.getAttribute('data-confirm');
    if (!message) { fn(); return; }
    EA.confirm(message, 'Выполнить').then(function (ok) { if (ok) fn(); });
  }
  document.querySelectorAll('[data-ea-action]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      confirmThen(btn, function () {
        runAction(btn, { url: btn.getAttribute('data-ea-action'), method: btn.getAttribute('data-method') });
      });
    });
  });
  document.querySelectorAll('[data-ea-action-upload]').forEach(function (btn) {
    var input = document.getElementById(btn.getAttribute('data-ea-action-upload'));
    btn.addEventListener('click', function () {
      confirmThen(btn, function () { input.value = ''; input.click(); });
    });
    input.addEventListener('change', function () {
      if (!input.files || !input.files[0]) return;
      var fd = new FormData();
      fd.append(input.getAttribute('data-field') || 'file', input.files[0]);
      runAction(btn, { url: input.getAttribute('data-url'), method: 'POST', body: fd });
    });
  });

  var SVG_NS = 'http://www.w3.org/2000/svg';
  function svgEl(tag, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    return node;
  }
  function niceMax(v) {
    if (v <= 4) return 4;
    var raw = v / 4;
    var p = Math.pow(10, Math.floor(Math.log10(raw)));
    var steps = [1, 2, 3, 5, 10];
    for (var i = 0; i < steps.length; i++) {
      var tick = Math.max(1, steps[i] * p);
      if (tick >= raw && Number.isInteger(tick)) return tick * 4;
    }
    return Math.ceil(raw) * 4;
  }
  function smoothPath(pts) {
    if (pts.length < 2) return '';
    var d = 'M' + pts[0][0] + ',' + pts[0][1];
    for (var i = 0; i < pts.length - 1; i++) {
      var p0 = pts[i - 1] || pts[i];
      var p1 = pts[i];
      var p2 = pts[i + 1];
      var p3 = pts[i + 2] || p2;
      var c1x = p1[0] + (p2[0] - p0[0]) / 6;
      var c1y = p1[1] + (p2[1] - p0[1]) / 6;
      var c2x = p2[0] - (p3[0] - p1[0]) / 6;
      var c2y = p2[1] - (p3[1] - p1[1]) / 6;
      var lo = Math.min(p1[1], p2[1]);
      var hi = Math.max(p1[1], p2[1]);
      c1y = Math.min(Math.max(c1y, lo), hi);
      c2y = Math.min(Math.max(c2y, lo), hi);
      d += ' C' + c1x + ',' + c1y + ' ' + c2x + ',' + c2y + ' ' + p2[0] + ',' + p2[1];
    }
    return d;
  }
  function drawChart(box, series, uid, animate) {
    box.innerHTML = '';
    var w = box.clientWidth - 20;
    var h = box.clientHeight - 26;
    if (w <= 0 || h <= 0) return;
    var padL = 36, padB = 26, padT = 8;
    var pts = series.points;
    var max = niceMax(Math.max.apply(null, pts.map(function (p) { return p.value; }).concat([0])));
    var plotW = w - padL;
    var plotH = h - padB - padT;
    var step = pts.length > 1 ? plotW / (pts.length - 1) : 0;
    var svg = svgEl('svg', { viewBox: '0 0 ' + w + ' ' + h, preserveAspectRatio: 'none' });
    var grad = svgEl('linearGradient', { id: 'eaFill' + uid, x1: 0, y1: 0, x2: 0, y2: 1 });
    grad.appendChild(svgEl('stop', { offset: '0%', style: 'stop-color: var(--ea-accent); stop-opacity: 0.34' }));
    grad.appendChild(svgEl('stop', { offset: '100%', style: 'stop-color: var(--ea-accent); stop-opacity: 0' }));
    var defs = svgEl('defs');
    defs.appendChild(grad);
    svg.appendChild(defs);
    for (var g = 0; g <= 4; g++) {
      var gy = padT + plotH - (plotH * g) / 4;
      svg.appendChild(svgEl('line', { x1: padL, x2: w, y1: gy, y2: gy, class: 'ea-chart-grid' }));
      var label = svgEl('text', { x: padL - 10, y: gy + 4, 'text-anchor': 'end', class: 'ea-chart-axis' });
      label.textContent = String(Math.round((max * g) / 4));
      svg.appendChild(label);
    }
    var xy = pts.map(function (p, i) {
      return [padL + i * step, padT + plotH - (p.value / max) * plotH];
    });
    var line = smoothPath(xy);
    var base = padT + plotH;
    var area = svgEl('path', { d: line + ' L' + xy[xy.length - 1][0] + ',' + base + ' L' + xy[0][0] + ',' + base + ' Z', fill: 'url(#eaFill' + uid + ')' });
    if (animate) area.setAttribute('class', 'ea-chart-area');
    svg.appendChild(area);
    var linePath = svgEl('path', { d: line, class: 'ea-chart-line' });
    svg.appendChild(linePath);
    var every = Math.max(1, Math.ceil(pts.length / Math.max(2, Math.floor(plotW / 64))));
    var dots = [];
    pts.forEach(function (p, i) {
      if (i % every === 0 || i === pts.length - 1) {
        var t = svgEl('text', { x: xy[i][0], y: h - 6, 'text-anchor': 'middle', class: 'ea-chart-axis' });
        t.textContent = p.label;
        svg.appendChild(t);
      }
      var dot = svgEl('circle', { cx: xy[i][0], cy: xy[i][1], r: 4, class: 'ea-chart-dot' });
      if (animate) dot.style.animationDelay = Math.round(150 + (i / Math.max(1, pts.length - 1)) * 850) + 'ms';
      else dot.style.animation = 'none';
      svg.appendChild(dot);
      dots.push(dot);
    });
    box.appendChild(svg);
    if (animate && linePath.getTotalLength) {
      var len = linePath.getTotalLength();
      linePath.style.transition = 'none';
      linePath.style.strokeDasharray = len + ' ' + len;
      linePath.style.strokeDashoffset = String(len);
      linePath.getBoundingClientRect();
      linePath.style.transition = '';
      requestAnimationFrame(function () { linePath.style.strokeDashoffset = '0'; });
      linePath.addEventListener('transitionend', function () {
        linePath.style.strokeDasharray = '';
        linePath.style.strokeDashoffset = '';
      }, { once: true });
    }

    var tip = el('div', 'ea-chart-tip');
    tip.hidden = true;
    box.appendChild(tip);
    svg.addEventListener('mousemove', function (e) {
      var rect = svg.getBoundingClientRect();
      var x = (e.clientX - rect.left) * (w / rect.width);
      var i = step ? Math.round((x - padL) / step) : 0;
      i = Math.max(0, Math.min(pts.length - 1, i));
      dots.forEach(function (d, k) { d.classList.toggle('is-hot', k === i); });
      tip.innerHTML = '';
      tip.appendChild(document.createTextNode(String(pts[i].value)));
      tip.appendChild(el('small', '', pts[i].label));
      tip.style.left = (xy[i][0] / w) * rect.width + 6 + 'px';
      tip.style.top = (xy[i][1] / h) * rect.height + 12 + 'px';
      tip.hidden = false;
    });
    svg.addEventListener('mouseleave', function () {
      tip.hidden = true;
      dots.forEach(function (d) { d.classList.remove('is-hot'); });
    });
  }
  document.querySelectorAll('[data-ea-chart]').forEach(function (card, n) {
    var data = [];
    try { data = JSON.parse(card.querySelector('[data-ea-chart-data]').textContent); } catch (e) { data = []; }
    if (!data.length) return;
    var box = card.querySelector('[data-ea-chart-canvas]');
    var current = 0;
    function render(animate) {
      var s = data[current];
      drawChart(box, s, n + '-' + current, animate && !reduceMotion);
      var title = card.querySelector('[data-ea-chart-title]');
      if (title) title.textContent = s.title;
      ['today', 'week', 'month'].forEach(function (k) {
        var t = card.querySelector('[data-ea-total="' + k + '"]');
        if (t) t.textContent = s[k];
      });
    }
    card.querySelectorAll('[data-ea-chart-tab]').forEach(function (tab) {
      tab.addEventListener('click', function () {
        current = parseInt(tab.getAttribute('data-ea-chart-tab'), 10) || 0;
        card.querySelectorAll('[data-ea-chart-tab]').forEach(function (t) {
          var on = t === tab;
          t.classList.toggle('is-active', on);
          t.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        render(true);
      });
    });
    render(true);
    var timer = null;
    window.addEventListener('resize', function () {
      clearTimeout(timer);
      timer = setTimeout(function () { render(false); }, 120);
    });
  });

  window.EA = EA;
})();
