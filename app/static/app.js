let booksCache = [];

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
  if (!el) return;
  el.textContent = msg;
  el.className = ok ? 'result ok' : 'result err';
}

function escapeHtml(v) {
  return String(v ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}

function conditionLabel(status) {
  if (status === 'damaged_needs_repair') return 'Damaged, needs repair';
  return 'Good';
}

function statusBadge(r) {
  const status = r.status || 'available';
  const condition = r.condition_status || 'good';
  let bits = [];
  if (status === 'borrowed') bits.push(`<span class="badge borrowed">Borrowed${r.borrowed_by ? ' by ' + escapeHtml(r.borrowed_by) : ''}</span>`);
  else bits.push(`<span class="badge available">Available</span>`);
  if (condition === 'damaged_needs_repair') bits.push(`<span class="badge damaged">Damaged, needs repair</span>`);
  return bits.join(' ');
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
    setResult('borrow-result', `🎉 ${r.child} borrowed “${r.title}”. Bring it back by ${r.due_at}.`);
    document.getElementById('borrow-book').value = '';
    document.getElementById('borrow-book').focus();
    await refreshAll();
  } catch (e) { setResult('borrow-result', e.message, false); }
}

async function returnBook() {
  try {
    const payload = { book_code: document.getElementById('return-book').value };
    const r = await api('/api/return', { method: 'POST', body: JSON.stringify(payload) });
    setResult('return-result', `✅ “${r.title}” is back from ${r.returned_from}.`);
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

function clearBookSearch() {
  document.getElementById('book-search').value = '';
  refreshBooks();
}

async function refreshBooks() {
  const q = document.getElementById('book-search')?.value?.trim() || '';
  const rows = await api('/api/books' + (q ? '?q=' + encodeURIComponent(q) : ''));
  booksCache = rows;
  const html = ['<tr><th>Cover</th><th>Title</th><th>Author / Illustrator</th><th>Category</th><th>ISBN</th><th>Qty</th><th>Barcode</th><th>Status</th><th>Actions</th></tr>']
    .concat(rows.map(r => `<tr>
      <td>${r.cover_url ? `<img class="cover-thumb" src="${escapeHtml(r.cover_url)}" alt="Cover" />` : ''}</td>
      <td><strong>${escapeHtml(r.title)}</strong>${r.synopsis ? `<div class="synopsis">${escapeHtml(r.synopsis)}</div>` : ''}${r.condition_note ? `<div class="condition-note">Note: ${escapeHtml(r.condition_note)}</div>` : ''}</td>
      <td>${escapeHtml(r.author)}${r.illustrator ? '<br><small>Illus. ' + escapeHtml(r.illustrator) + '</small>' : ''}</td>
      <td>${escapeHtml(r.category)}</td>
      <td>${escapeHtml(r.isbn)}</td>
      <td>${escapeHtml(r.owned_qty || 1)}</td>
      <td>${escapeHtml(r.barcode)}</td>
      <td>${statusBadge(r)}</td>
      <td class="actions">
        <button class="small" onclick="editBook(${r.book_id}, ${r.copy_id})">Edit</button>
        ${r.condition_status === 'damaged_needs_repair'
          ? `<button class="small secondary" onclick="markCondition(${r.copy_id}, 'good')">Mark repaired</button>`
          : `<button class="small warning" onclick="markCondition(${r.copy_id}, 'damaged_needs_repair')">Damaged</button>`}
        <button class="small danger" onclick="deleteBook(${r.book_id})">Delete</button>
      </td>
    </tr>`));
  document.getElementById('books-table').innerHTML = html.join('');
}

async function refreshLoans() {
  const rows = await api('/api/loans');
  const html = ['<tr><th>Reader</th><th>Book</th><th>Due</th><th>Barcode</th></tr>']
    .concat(rows.map(r => `<tr><td>${escapeHtml(r.child)}</td><td>📖 ${escapeHtml(r.title)}</td><td>${escapeHtml((r.due_at || '').slice(0,10))}</td><td>${escapeHtml(r.barcode)}</td></tr>`));
  document.getElementById('loans-table').innerHTML = html.join('');
}

function editBook(bookId, copyId) {
  const r = booksCache.find(x => x.book_id === bookId && x.copy_id === copyId);
  if (!r) return;
  document.getElementById('edit-book-id').value = r.book_id;
  document.getElementById('edit-copy-id').value = r.copy_id;
  document.getElementById('edit-title').value = r.title || '';
  document.getElementById('edit-author').value = r.author || '';
  document.getElementById('edit-illustrator').value = r.illustrator || '';
  document.getElementById('edit-synopsis').value = r.synopsis || '';
  document.getElementById('edit-category').value = r.category || '';
  document.getElementById('edit-isbn').value = r.isbn || '';
  document.getElementById('edit-barcode').value = r.barcode || '';
  document.getElementById('edit-qty').value = r.owned_qty || 1;
  document.getElementById('edit-cover').value = r.cover_url || '';
  document.getElementById('edit-shelf').value = r.shelf_location || '';
  document.getElementById('edit-condition').value = r.condition_status || 'good';
  document.getElementById('edit-condition-note').value = r.condition_note || '';
  document.getElementById('edit-card').hidden = false;
  document.getElementById('edit-result').textContent = '';
  document.getElementById('edit-card').scrollIntoView({ behaviour: 'smooth', block: 'start' });
}

function cancelEdit() {
  document.getElementById('edit-card').hidden = true;
}

async function saveEdit() {
  try {
    const bookId = Number(document.getElementById('edit-book-id').value);
    const payload = {
      copy_id: Number(document.getElementById('edit-copy-id').value),
      title: document.getElementById('edit-title').value,
      author: document.getElementById('edit-author').value,
      illustrator: document.getElementById('edit-illustrator').value,
      synopsis: document.getElementById('edit-synopsis').value,
      category: document.getElementById('edit-category').value,
      isbn: document.getElementById('edit-isbn').value,
      barcode: document.getElementById('edit-barcode').value,
      owned_qty: Number(document.getElementById('edit-qty').value || 1),
      cover_url: document.getElementById('edit-cover').value,
      shelf_location: document.getElementById('edit-shelf').value,
      condition_status: document.getElementById('edit-condition').value,
      condition_note: document.getElementById('edit-condition-note').value
    };
    await api('/api/books/' + bookId, { method: 'PUT', body: JSON.stringify(payload) });
    setResult('edit-result', 'Book updated.');
    await refreshBooks();
  } catch (e) { setResult('edit-result', e.message, false); }
}

async function markCondition(copyId, conditionStatus) {
  const note = conditionStatus === 'damaged_needs_repair'
    ? prompt('Damage/repair note?', 'Needs repair')
    : '';
  if (conditionStatus === 'damaged_needs_repair' && note === null) return;
  try {
    await api('/api/book-copies/' + copyId + '/condition', {
      method: 'PATCH',
      body: JSON.stringify({ condition_status: conditionStatus, condition_note: note })
    });
    await refreshBooks();
  } catch (e) { alert(e.message); }
}

async function deleteBook(bookId) {
  const r = booksCache.find(x => x.book_id === bookId);
  const title = r ? r.title : 'this book';
  if (!confirm(`Delete “${title}” from ShelfQuest? This hides it from the catalogue but keeps historical loan records.`)) return;
  try {
    await api('/api/books/' + bookId, { method: 'DELETE' });
    await refreshBooks();
    await refreshLoans();
  } catch (e) { alert(e.message); }
}

async function refreshAll() {
  await Promise.all([refreshChildren(), refreshBooks(), refreshLoans()]);
}

window.addEventListener('load', refreshAll);

window.addEventListener('load', () => {
  ['borrow-book', 'return-book', 'isbn'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('keydown', e => {
      if (e.key !== 'Enter') return;
      if (id === 'borrow-book') checkout();
      if (id === 'return-book') returnBook();
      if (id === 'isbn') lookupBook();
    });
  });

  const search = document.getElementById('book-search');
  if (search) {
    let timer;
    search.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(refreshBooks, 250);
    });
    search.addEventListener('keydown', e => {
      if (e.key === 'Enter') refreshBooks();
    });
  }
});
