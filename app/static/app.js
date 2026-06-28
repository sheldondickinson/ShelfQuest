function showTab(id) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || 'Request failed');
  return body;
}

function setResult(id, msg, ok = true) {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.className = ok ? 'result ok' : 'result err';
}

function escapeHtml(v) {
  return String(v ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}

async function addChild() {
  try {
    const payload = {
      name: document.getElementById('child-name').value,
      barcode: document.getElementById('child-barcode').value,
      borrow_limit: Number(document.getElementById('child-limit').value || 5)
    };
    await api('/api/children', { method: 'POST', body: JSON.stringify(payload) });
    setResult('child-result', 'Child added.');
    await refreshAll();
  } catch (e) { setResult('child-result', e.message, false); }
}

async function lookupBook() {
  const isbn = document.getElementById('isbn').value.trim();
  if (!isbn) return setResult('book-result', 'Scan or enter an ISBN first.', false);
  try {
    const b = await api('/api/lookup/' + encodeURIComponent(isbn));
    document.getElementById('book-title').value = b.title || '';
    document.getElementById('book-author').value = b.author || '';
    document.getElementById('book-cover').value = b.cover_url || '';
    document.getElementById('book-barcode').value = b.isbn || isbn;
    setResult('book-result', `Found via ${b.source}. Check details, then Add Book.`);
  } catch (e) {
    document.getElementById('book-barcode').value = isbn;
    setResult('book-result', e.message + ' Enter details manually.', false);
  }
}

async function addBook() {
  try {
    const isbn = document.getElementById('isbn').value.trim();
    const payload = {
      isbn,
      title: document.getElementById('book-title').value,
      author: document.getElementById('book-author').value,
      illustrator: document.getElementById('book-illustrator').value,
      synopsis: document.getElementById('book-synopsis').value,
      owned_qty: Number(document.getElementById('book-qty').value || 1),
      cover_url: document.getElementById('book-cover').value,
      category: document.getElementById('book-category').value,
      barcode: document.getElementById('book-barcode').value || isbn
    };
    await api('/api/books', { method: 'POST', body: JSON.stringify(payload) });
    setResult('book-result', 'Book added.');
    await refreshAll();
  } catch (e) { setResult('book-result', e.message, false); }
}

async function checkout() {
  try {
    const payload = {
      child_barcode: document.getElementById('borrow-child').value,
      book_code: document.getElementById('borrow-book').value
    };
    const r = await api('/api/checkout', { method: 'POST', body: JSON.stringify(payload) });
    setResult('borrow-result', `${r.child} borrowed ${r.title}. Due ${r.due_at}.`);
    document.getElementById('borrow-book').value = '';
    document.getElementById('borrow-book').focus();
    await refreshAll();
  } catch (e) { setResult('borrow-result', e.message, false); }
}

async function returnBook() {
  try {
    const payload = { book_code: document.getElementById('return-book').value };
    const r = await api('/api/return', { method: 'POST', body: JSON.stringify(payload) });
    setResult('return-result', `${r.title} returned from ${r.returned_from}.`);
    document.getElementById('return-book').value = '';
    document.getElementById('return-book').focus();
    await refreshAll();
  } catch (e) { setResult('return-result', e.message, false); }
}

async function refreshChildren() {
  const rows = await api('/api/children');
  const html = ['<tr><th>Name</th><th>Card</th><th>Limit</th><th>Borrowed</th></tr>']
    .concat(rows.map(r => `<tr><td>${escapeHtml(r.name)}</td><td>${escapeHtml(r.barcode)}</td><td>${r.borrow_limit}</td><td>${r.active_loans}</td></tr>`));
  document.getElementById('children-table').innerHTML = html.join('');
}

async function refreshBooks() {
  const rows = await api('/api/books');
  const html = ['<tr><th>Cover</th><th>Title</th><th>Author / Illustrator</th><th>Category</th><th>ISBN</th><th>Qty</th><th>Barcode</th><th>Status</th></tr>']
    .concat(rows.map(r => `<tr><td>${r.cover_url ? `<img class="cover-thumb" src="${escapeHtml(r.cover_url)}" alt="Cover" />` : ''}</td><td><strong>${escapeHtml(r.title)}</strong>${r.synopsis ? `<div class="synopsis">${escapeHtml(r.synopsis)}</div>` : ''}</td><td>${escapeHtml(r.author)}${r.illustrator ? '<br><small>Illus. ' + escapeHtml(r.illustrator) + '</small>' : ''}</td><td>${escapeHtml(r.category)}</td><td>${escapeHtml(r.isbn)}</td><td>${escapeHtml(r.owned_qty || 1)}</td><td>${escapeHtml(r.barcode)}</td><td>${escapeHtml(r.status)}${r.borrowed_by ? ' by ' + escapeHtml(r.borrowed_by) : ''}</td></tr>`));
  document.getElementById('books-table').innerHTML = html.join('');
}

async function refreshLoans() {
  const rows = await api('/api/loans');
  const html = ['<tr><th>Child</th><th>Book</th><th>Due</th><th>Barcode</th></tr>']
    .concat(rows.map(r => `<tr><td>${escapeHtml(r.child)}</td><td>${escapeHtml(r.title)}</td><td>${escapeHtml((r.due_at || '').slice(0,10))}</td><td>${escapeHtml(r.barcode)}</td></tr>`));
  document.getElementById('loans-table').innerHTML = html.join('');
}

async function refreshAll() {
  await Promise.all([refreshChildren(), refreshBooks(), refreshLoans()]);
}

window.addEventListener('load', refreshAll);

['borrow-book', 'return-book', 'isbn'].forEach(id => {
  window.addEventListener('load', () => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('keydown', e => {
      if (e.key !== 'Enter') return;
      if (id === 'borrow-book') checkout();
      if (id === 'return-book') returnBook();
      if (id === 'isbn') lookupBook();
    });
  });
});
