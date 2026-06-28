let booksCache = [];
let childrenCache = [];
let kidSearchCache = [];
let currentBookPage = 1;
let bookPageSize = 25;
let scannerStream = null;
let scannerLoop = null;
let scannerTargetInputId = null;
let scannerAfterScan = null;

function adminToken() {
  return localStorage.getItem('shelfquest_admin_token') || '';
}

function adminUnlocked() {
  return Boolean(adminToken());
}

function showTab(id) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  if (id === 'admin') updateAdminLockState();
}

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  const token = adminToken();
  if (token) headers['X-Admin-Token'] = token;
  const res = await fetch(path, { ...opts, headers });
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

function kidStatusText(r) {
  if ((r.condition_status || 'good') === 'damaged_needs_repair') return 'Needs repair';
  if ((r.status || 'available') === 'borrowed') return r.borrowed_by ? `Borrowed by ${r.borrowed_by}` : 'Borrowed';
  return 'Ready to borrow';
}

function coverImg(r, className = 'cover-thumb') {
  return r.cover_url ? `<img class="${className}" src="${escapeHtml(r.cover_url)}" alt="Cover for ${escapeHtml(r.title)}" loading="lazy" />` : `<div class="${className} cover-placeholder">📘</div>`;
}

function childPhoto(child, className = 'child-photo') {
  const initials = String(child.name || '?').trim().slice(0,1).toUpperCase() || '?';
  return child.photo_url
    ? `<img class="${className}" src="${escapeHtml(child.photo_url)}" alt="Photo of ${escapeHtml(child.name)}" loading="lazy" />`
    : `<div class="${className} child-placeholder">${escapeHtml(initials)}</div>`;
}

async function adminLogin() {
  try {
    const password = document.getElementById('admin-password').value;
    const r = await api('/api/admin/login', { method: 'POST', body: JSON.stringify({ password }) });
    localStorage.setItem('shelfquest_admin_token', r.token);
    document.getElementById('admin-password').value = '';
    setResult('admin-login-result', 'Admin unlocked.');
    updateAdminLockState();
    await refreshAll();
  } catch (e) {
    localStorage.removeItem('shelfquest_admin_token');
    updateAdminLockState();
    setResult('admin-login-result', e.message, false);
  }
}

function adminLogout() {
  localStorage.removeItem('shelfquest_admin_token');
  updateAdminLockState();
}

function updateAdminLockState() {
  const login = document.getElementById('admin-login-card');
  const content = document.getElementById('admin-content');
  if (!login || !content) return;
  const unlocked = adminUnlocked();
  login.hidden = unlocked;
  content.hidden = !unlocked;
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
    document.getElementById('child-name').value = '';
    document.getElementById('child-barcode').value = '';
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

function selectedChildBarcode() {
  const scanned = document.getElementById('borrow-child')?.value?.trim() || '';
  const selected = document.getElementById('kid-child-select')?.value?.trim() || '';
  return scanned || selected;
}

function selectKidReader(barcode) {
  const select = document.getElementById('kid-child-select');
  const scan = document.getElementById('borrow-child');
  if (select) select.value = barcode;
  if (scan) scan.value = '';
  document.getElementById('borrow-book')?.focus();
}

async function checkout() {
  try {
    const payload = {
      child_barcode: selectedChildBarcode(),
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
  childrenCache = rows;
  const html = ['<tr><th>Photo</th><th>Name</th><th>Card</th><th>Limit</th><th>Borrowed</th><th>Actions</th></tr>']
    .concat(rows.map(r => `<tr>
      <td>${childPhoto(r, 'child-photo table-child-photo')}</td>
      <td>${escapeHtml(r.name)}</td>
      <td>${escapeHtml(r.barcode)}</td>
      <td>${r.borrow_limit}</td>
      <td>${r.active_loans}</td>
      <td>${adminUnlocked() ? `<button class="small" onclick="editChild(${r.id})">Edit</button>` : ''}</td>
    </tr>`));
  const childrenTable = document.getElementById('children-table');
  if (childrenTable) childrenTable.innerHTML = html.join('');

  const select = document.getElementById('kid-child-select');
  if (select) {
    const current = select.value;
    select.innerHTML = '<option value="">Choose your card</option>' + rows.map(r => `<option value="${escapeHtml(r.barcode)}">${escapeHtml(r.name)} (${r.active_loans}/${r.borrow_limit})</option>`).join('');
    if (rows.some(r => r.barcode === current)) select.value = current;
  }

  const pickers = document.getElementById('kid-reader-pickers');
  if (pickers) {
    pickers.innerHTML = rows.map(r => `
      <button class="reader-picker" type="button" onclick="selectKidReader('${escapeHtml(r.barcode)}')">
        ${childPhoto(r, 'reader-photo')}
        <span>${escapeHtml(r.name)}</span>
        <small>${r.active_loans}/${r.borrow_limit}</small>
      </button>
    `).join('');
  }
}

function editChild(childId) {
  const r = childrenCache.find(x => x.id === childId);
  if (!r) return;
  document.getElementById('edit-child-id').value = r.id;
  document.getElementById('edit-child-name').value = r.name || '';
  document.getElementById('edit-child-barcode').value = r.barcode || '';
  document.getElementById('edit-child-limit').value = r.borrow_limit || 5;
  document.getElementById('edit-child-active').value = String(r.active ?? 1);
  document.getElementById('edit-child-photo-file').value = '';
  document.getElementById('edit-child-photo-preview').innerHTML = childPhoto(r, 'child-photo-large');
  document.getElementById('edit-child-card').hidden = false;
  document.getElementById('edit-child-result').textContent = '';
  document.getElementById('child-photo-result').textContent = '';
  document.getElementById('edit-child-card').scrollIntoView({ behaviour: 'smooth', block: 'start' });
}

function cancelChildEdit() {
  document.getElementById('edit-child-card').hidden = true;
}

async function saveChildEdit() {
  try {
    const childId = Number(document.getElementById('edit-child-id').value);
    const payload = {
      name: document.getElementById('edit-child-name').value,
      barcode: document.getElementById('edit-child-barcode').value,
      borrow_limit: Number(document.getElementById('edit-child-limit').value || 5),
      active: Number(document.getElementById('edit-child-active').value || 1)
    };
    await api('/api/children/' + childId, { method: 'PUT', body: JSON.stringify(payload) });
    setResult('edit-child-result', 'Child updated.');
    await refreshChildren();
  } catch (e) { setResult('edit-child-result', e.message, false); }
}

async function uploadChildPhoto() {
  const childId = Number(document.getElementById('edit-child-id').value);
  const file = document.getElementById('edit-child-photo-file').files[0];
  if (!childId) return setResult('child-photo-result', 'Open a child for editing first.', false);
  if (!file) return setResult('child-photo-result', 'Choose an image file first.', false);
  try {
    setResult('child-photo-result', 'Uploading photo...');
    const data = await fileToBase64(file);
    const r = await api('/api/children/' + childId + '/photo', {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, content_type: file.type, data_base64: data })
    });
    setResult('child-photo-result', 'Photo uploaded.');
    await refreshChildren();
    const child = childrenCache.find(x => x.id === childId) || {name: '', photo_url: r.photo_url};
    child.photo_url = r.photo_url;
    document.getElementById('edit-child-photo-preview').innerHTML = childPhoto(child, 'child-photo-large');
  } catch (e) { setResult('child-photo-result', e.message, false); }
}

function clearBookSearch() {
  document.getElementById('book-search').value = '';
  currentBookPage = 1;
  refreshBooks();
}

async function refreshBooks() {
  const q = document.getElementById('book-search')?.value?.trim() || '';
  const rows = await api('/api/books' + (q ? '?q=' + encodeURIComponent(q) : ''));
  booksCache = rows;
  currentBookPage = 1;
  renderBooksPage();
}

function renderBooksPage() {
  const total = booksCache.length;
  const totalPages = Math.max(1, Math.ceil(total / bookPageSize));
  currentBookPage = Math.min(Math.max(1, currentBookPage), totalPages);
  const start = (currentBookPage - 1) * bookPageSize;
  const pageRows = booksCache.slice(start, start + bookPageSize);

  const summary = document.getElementById('book-page-summary');
  if (summary) {
    const end = total ? Math.min(start + bookPageSize, total) : 0;
    summary.textContent = total ? `Showing ${start + 1}-${end} of ${total} books` : 'No books found';
  }
  const indicator = document.getElementById('book-page-indicator');
  if (indicator) indicator.textContent = `Page ${currentBookPage} of ${totalPages}`;

  const html = ['<tr><th>Cover</th><th>Title</th><th>Author / Illustrator</th><th>Category</th><th>ISBN</th><th>Qty</th><th>Barcode</th><th>Status</th><th>Actions</th></tr>']
    .concat(pageRows.map(r => `<tr>
      <td data-label="Cover">${coverImg(r, 'cover-thumb')}</td>
      <td data-label="Title"><strong>${escapeHtml(r.title)}</strong>${r.synopsis ? `<div class="synopsis">${escapeHtml(r.synopsis)}</div>` : ''}${r.condition_note ? `<div class="condition-note">Note: ${escapeHtml(r.condition_note)}</div>` : ''}</td>
      <td data-label="Author / Illustrator">${escapeHtml(r.author)}${r.illustrator ? '<br><small>Illus. ' + escapeHtml(r.illustrator) + '</small>' : ''}</td>
      <td data-label="Category">${escapeHtml(r.category)}</td>
      <td data-label="ISBN">${escapeHtml(r.isbn)}</td>
      <td data-label="Qty">${escapeHtml(r.owned_qty || 1)}</td>
      <td data-label="Barcode">${escapeHtml(r.barcode)}</td>
      <td data-label="Status">${statusBadge(r)}</td>
      <td data-label="Actions" class="actions">
        ${adminUnlocked() ? `<button class="small" onclick="editBook(${r.book_id}, ${r.copy_id})">Edit</button>` : ''}
        ${adminUnlocked() ? (r.condition_status === 'damaged_needs_repair'
          ? `<button class="small secondary" onclick="markCondition(${r.copy_id}, 'good')">Mark repaired</button>`
          : `<button class="small warning" onclick="markCondition(${r.copy_id}, 'damaged_needs_repair')">Damaged</button>`) : ''}
        ${adminUnlocked() ? `<button class="small danger" onclick="deleteBook(${r.book_id})">Delete</button>` : ''}
      </td>
    </tr>`));
  const table = document.getElementById('books-table');
  if (table) table.innerHTML = html.join('');
}

function prevBookPage() {
  currentBookPage -= 1;
  renderBooksPage();
}

function nextBookPage() {
  currentBookPage += 1;
  renderBooksPage();
}

function changeBookPageSize() {
  bookPageSize = Number(document.getElementById('book-page-size').value || 25);
  currentBookPage = 1;
  renderBooksPage();
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
  document.getElementById('edit-cover-file').value = '';
  document.getElementById('edit-card').hidden = false;
  document.getElementById('edit-result').textContent = '';
  document.getElementById('cover-result').textContent = '';
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

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || '');
      resolve(value.includes(',') ? value.split(',')[1] : value);
    };
    reader.onerror = () => reject(reader.error || new Error('Could not read file'));
    reader.readAsDataURL(file);
  });
}

async function uploadEditCover() {
  const bookId = Number(document.getElementById('edit-book-id').value);
  const file = document.getElementById('edit-cover-file').files[0];
  if (!bookId) return setResult('cover-result', 'Open a book for editing first.', false);
  if (!file) return setResult('cover-result', 'Choose an image file first.', false);
  try {
    setResult('cover-result', 'Uploading cover...');
    const data = await fileToBase64(file);
    const r = await api('/api/books/' + bookId + '/cover', {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, content_type: file.type, data_base64: data })
    });
    document.getElementById('edit-cover').value = r.cover_url;
    setResult('cover-result', 'Cover uploaded to the NAS. Save other changes if needed.');
    await refreshBooks();
  } catch (e) { setResult('cover-result', e.message, false); }
}

async function cacheRemoteCovers() {
  if (!confirm('Copy all remote CoverURL images into the QNAP /data/covers folder? This may take a minute.')) return;
  try {
    setResult('cover-result', 'Copying cover images to NAS...');
    const r = await api('/api/covers/cache', { method: 'POST', body: JSON.stringify({}) });
    const failed = r.failed_count ? ` ${r.failed_count} failed.` : '';
    setResult('cover-result', `Copied ${r.cached} covers. Skipped ${r.skipped}.${failed}`);
    await refreshBooks();
  } catch (e) { setResult('cover-result', e.message, false); }
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

async function kidSearchBooks() {
  const q = document.getElementById('kid-search').value.trim();
  const target = document.getElementById('kid-search-results');
  if (!q) {
    target.innerHTML = '<p class="kid-hint">Type something to find a book.</p>';
    return;
  }
  try {
    const rows = await api('/api/books?q=' + encodeURIComponent(q));
    kidSearchCache = rows.slice(0, 24);
    if (!kidSearchCache.length) {
      target.innerHTML = '<p class="kid-hint">No books found. Try another word.</p>';
      return;
    }
    target.innerHTML = kidSearchCache.map((r, idx) => `
      <button class="kid-book-result" onclick="showBookModal(${idx})">
        ${coverImg(r, 'kid-result-cover')}
        <span class="kid-result-title">${escapeHtml(r.title)}</span>
        <span class="kid-result-meta">${escapeHtml(r.author || r.category || '')}</span>
        <span class="kid-result-status">${escapeHtml(kidStatusText(r))}</span>
      </button>
    `).join('');
  } catch (e) {
    target.innerHTML = `<p class="kid-hint error">${escapeHtml(e.message)}</p>`;
  }
}

function showBookModal(index) {
  const r = kidSearchCache[index];
  if (!r) return;
  const status = kidStatusText(r);
  const canBorrow = status === 'Ready to borrow';
  document.getElementById('book-modal-content').innerHTML = `
    <div class="modal-book">
      <div>${coverImg(r, 'modal-cover')}</div>
      <div>
        <h2 id="modal-title">${escapeHtml(r.title)}</h2>
        ${r.author ? `<p><strong>Author:</strong> ${escapeHtml(r.author)}</p>` : ''}
        ${r.illustrator ? `<p><strong>Illustrator:</strong> ${escapeHtml(r.illustrator)}</p>` : ''}
        ${r.category ? `<p><strong>Shelf:</strong> ${escapeHtml(r.category)}</p>` : ''}
        ${r.shelf_location ? `<p><strong>Location:</strong> ${escapeHtml(r.shelf_location)}</p>` : ''}
        <p><strong>Status:</strong> ${escapeHtml(status)}</p>
        ${r.synopsis ? `<p class="modal-synopsis">${escapeHtml(r.synopsis)}</p>` : '<p class="modal-synopsis">No story blurb yet.</p>'}
        <div class="modal-action-note">${canBorrow ? 'Found it? Scan the book barcode to borrow it.' : 'Ask a grown-up about this one.'}</div>
      </div>
    </div>
  `;
  document.getElementById('book-modal').hidden = false;
}

function closeBookModal() {
  document.getElementById('book-modal').hidden = true;
}

async function openBarcodeScanner(targetInputId, afterScan = null) {
  scannerTargetInputId = targetInputId;
  scannerAfterScan = afterScan;
  const modal = document.getElementById('scanner-modal');
  const video = document.getElementById('scanner-video');
  const result = document.getElementById('scanner-result');
  const help = document.getElementById('scanner-help');
  modal.hidden = false;
  result.textContent = '';

  if (!('BarcodeDetector' in window)) {
    help.textContent = 'Camera barcode scanning is not available in this browser. Use a USB scanner, type the barcode, or try a Chromium-based browser over HTTPS.';
    result.textContent = 'Barcode detector unavailable.';
    return;
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    help.textContent = 'Camera access is not available. Mobile browsers often require HTTPS for camera scanning.';
    result.textContent = 'Camera unavailable.';
    return;
  }

  try {
    scannerStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
    video.srcObject = scannerStream;
    await video.play();
    const detector = new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39', 'itf', 'codabar', 'qr_code'] });
    help.textContent = 'Point your camera at the barcode. It will fill the field automatically.';

    const tick = async () => {
      if (!scannerStream) return;
      try {
        const codes = await detector.detect(video);
        if (codes && codes.length) {
          const value = codes[0].rawValue || '';
          const input = document.getElementById(scannerTargetInputId);
          if (input) {
            input.value = value;
            input.dispatchEvent(new Event('input', { bubbles: true }));
          }
          closeBarcodeScanner();
          if (typeof scannerAfterScan === 'function') scannerAfterScan();
          return;
        }
      } catch (err) {
        result.textContent = err.message || 'Scanning failed.';
      }
      scannerLoop = requestAnimationFrame(tick);
    };
    tick();
  } catch (e) {
    help.textContent = 'Could not open the camera. Try HTTPS, grant camera permission, or use the USB scanner/manual entry.';
    result.textContent = e.message || 'Camera failed.';
  }
}

function closeBarcodeScanner() {
  if (scannerLoop) cancelAnimationFrame(scannerLoop);
  scannerLoop = null;
  const video = document.getElementById('scanner-video');
  if (video) video.pause();
  if (scannerStream) {
    scannerStream.getTracks().forEach(track => track.stop());
    scannerStream = null;
  }
  const modal = document.getElementById('scanner-modal');
  if (modal) modal.hidden = true;
}

async function refreshAll() {
  try {
    await Promise.all([refreshChildren(), refreshBooks(), refreshLoans()]);
  } catch (e) {
    console.error(e);
  }
}

window.addEventListener('load', () => {
  updateAdminLockState();
  refreshAll();

  ['borrow-book', 'return-book', 'isbn', 'kid-search', 'admin-password'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('keydown', e => {
      if (e.key !== 'Enter') return;
      if (id === 'borrow-book') checkout();
      if (id === 'return-book') returnBook();
      if (id === 'isbn') lookupBook();
      if (id === 'kid-search') kidSearchBooks();
      if (id === 'admin-password') adminLogin();
    });
  });

  const childSelect = document.getElementById('kid-child-select');
  if (childSelect) {
    childSelect.addEventListener('change', () => {
      const scan = document.getElementById('borrow-child');
      if (scan) scan.value = '';
      document.getElementById('borrow-book')?.focus();
    });
  }

  const scanCard = document.getElementById('borrow-child');
  if (scanCard) {
    scanCard.addEventListener('input', () => {
      const select = document.getElementById('kid-child-select');
      if (select && scanCard.value.trim()) select.value = '';
    });
  }

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

  const size = document.getElementById('book-page-size');
  if (size) bookPageSize = Number(size.value || 25);
});
