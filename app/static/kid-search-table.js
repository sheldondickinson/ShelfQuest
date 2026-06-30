let currentKidSearchPage = 1;
let kidSearchPageSize = 10;
let lastKidSearchQuery = '';
let kidCatalogueRows = [];
let quickBorrowBookCode = '';

const BOOK_FILTER_FIELDS = [
  ['all', 'All fields'],
  ['title', 'Title'],
  ['author', 'Author'],
  ['illustrator', 'Illustrator'],
  ['category', 'Category'],
  ['shelf', 'Shelf'],
  ['synopsis', 'Synopsis'],
  ['status', 'Status'],
  ['code', 'ISBN / barcode']
];

const BOOK_STATUS_FILTERS = [
  ['all', 'All statuses'],
  ['available', 'Available'],
  ['borrowed', 'Borrowed'],
  ['damaged', 'Needs repair']
];

function normaliseFilterText(value) {
  return String(value ?? '').trim().toLowerCase();
}

function bookStatusTextForFilter(r) {
  const bits = [];
  const status = r.status || 'available';
  const condition = r.condition_status || 'good';
  bits.push(status === 'borrowed' ? 'borrowed' : 'available');
  if (r.borrowed_by) bits.push(r.borrowed_by);
  if (condition === 'damaged_needs_repair') bits.push('damaged needs repair repair');
  else bits.push('good');
  bits.push(kidStatusText(r));
  return bits.join(' ');
}

function bookFieldValues(r, field) {
  const values = {
    title: [r.title],
    author: [r.author],
    illustrator: [r.illustrator],
    category: [r.category],
    shelf: [r.shelf_location, r.category],
    synopsis: [r.synopsis],
    status: [bookStatusTextForFilter(r)],
    code: [r.isbn, r.barcode]
  };
  if (field && field !== 'all') return values[field] || [];
  return [
    r.title,
    r.author,
    r.illustrator,
    r.category,
    r.shelf_location,
    r.synopsis,
    r.isbn,
    r.barcode,
    r.condition_note,
    bookStatusTextForFilter(r)
  ];
}

function rowMatchesTextFilter(r, query, field) {
  const q = normaliseFilterText(query);
  if (!q) return true;
  const haystack = bookFieldValues(r, field).map(v => normaliseFilterText(v)).join(' ');
  return q.split(/\s+/).every(term => haystack.includes(term));
}

function rowMatchesStatusFilter(r, statusFilter) {
  if (!statusFilter || statusFilter === 'all') return true;
  const status = r.status || 'available';
  const condition = r.condition_status || 'good';
  if (statusFilter === 'available') return status !== 'borrowed';
  if (statusFilter === 'borrowed') return status === 'borrowed';
  if (statusFilter === 'damaged') return condition === 'damaged_needs_repair';
  return true;
}

function filterBookRows(rows, filters) {
  return rows.filter(r =>
    rowMatchesTextFilter(r, filters.query, filters.field) &&
    rowMatchesStatusFilter(r, filters.status)
  );
}

function filterSelectOptions(options, selected = 'all') {
  return options.map(([value, label]) => `<option value="${escapeHtml(value)}" ${value === selected ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('');
}

function getKidFilters() {
  return {
    query: document.getElementById('kid-search')?.value?.trim() || '',
    field: document.getElementById('kid-search-field')?.value || 'all',
    status: document.getElementById('kid-status-filter')?.value || 'all'
  };
}

function getAdminBookFilters() {
  return {
    query: document.getElementById('book-search')?.value?.trim() || '',
    field: document.getElementById('book-search-field')?.value || 'all',
    status: document.getElementById('book-status-filter')?.value || 'all'
  };
}

function ensureKidFilterControls() {
  if (document.getElementById('kid-catalogue-filter-row')) return;
  const results = document.getElementById('kid-search-results');
  if (!results) return;
  const filterRow = document.createElement('div');
  filterRow.id = 'kid-catalogue-filter-row';
  filterRow.className = 'catalogue-filter-row kid-catalogue-filter-row';
  filterRow.innerHTML = `
    <label>
      <span>Search in</span>
      <select id="kid-search-field" aria-label="Choose which book field to search">
        ${filterSelectOptions(BOOK_FILTER_FIELDS)}
      </select>
    </label>
    <label>
      <span>Status</span>
      <select id="kid-status-filter" aria-label="Filter books by status">
        ${filterSelectOptions(BOOK_STATUS_FILTERS)}
      </select>
    </label>
  `;
  results.parentNode.insertBefore(filterRow, results);

  document.getElementById('kid-search-field')?.addEventListener('change', () => kidSearchBooks());
  document.getElementById('kid-status-filter')?.addEventListener('change', () => kidSearchBooks());
}

function ensureAdminFilterControls() {
  if (document.getElementById('admin-catalogue-filter-row')) return;
  const booksCard = document.getElementById('books-card');
  const result = document.getElementById('books-result');
  if (!booksCard || !result) return;
  const filterRow = document.createElement('div');
  filterRow.id = 'admin-catalogue-filter-row';
  filterRow.className = 'catalogue-filter-row admin-catalogue-filter-row';
  filterRow.innerHTML = `
    <label>
      <span>Search in</span>
      <select id="book-search-field" aria-label="Choose which book field to search">
        ${filterSelectOptions(BOOK_FILTER_FIELDS)}
      </select>
    </label>
    <label>
      <span>Status</span>
      <select id="book-status-filter" aria-label="Filter books by status">
        ${filterSelectOptions(BOOK_STATUS_FILTERS)}
      </select>
    </label>
  `;
  booksCard.insertBefore(filterRow, result);

  document.getElementById('book-search-field')?.addEventListener('change', () => refreshBooks());
  document.getElementById('book-status-filter')?.addEventListener('change', () => refreshBooks());
}

async function loadKidCatalogueRows(forceReload = false) {
  if (!forceReload && kidCatalogueRows.length) return kidCatalogueRows;
  kidCatalogueRows = await api('/api/books');
  return kidCatalogueRows;
}

function clearKidSearch() {
  const input = document.getElementById('kid-search');
  if (input) input.value = '';
  const field = document.getElementById('kid-search-field');
  if (field) field.value = 'all';
  const status = document.getElementById('kid-status-filter');
  if (status) status.value = 'all';
  currentKidSearchPage = 1;
  lastKidSearchQuery = '';
  kidSearchBooks();
  input?.focus();
}

async function kidSearchBooks(options = {}) {
  const target = document.getElementById('kid-search-results');
  if (!target) return;
  ensureKidFilterControls();

  try {
    target.classList.add('kid-catalogue-results');
    if (!kidCatalogueRows.length) target.innerHTML = '<p class="kid-hint">Loading the shelves...</p>';
    const rows = await loadKidCatalogueRows(Boolean(options.forceReload));
    const filters = getKidFilters();
    kidSearchCache = filterBookRows(rows, filters);
    lastKidSearchQuery = filters.query;
    currentKidSearchPage = 1;
    renderKidSearchPage(filters, rows.length);
  } catch (e) {
    target.innerHTML = `<p class="kid-hint error">${escapeHtml(e.message)}</p>`;
  }
}

function renderKidSearchPage(filters = getKidFilters(), catalogueTotal = kidCatalogueRows.length) {
  const target = document.getElementById('kid-search-results');
  if (!target) return;

  target.classList.add('kid-catalogue-results');

  const total = kidSearchCache.length;
  if (!total) {
    const hasFilter = Boolean(filters.query || filters.field !== 'all' || filters.status !== 'all');
    target.innerHTML = `<p class="kid-hint">${hasFilter ? 'No books match those filters. Try widening the search.' : 'No books are in the catalogue yet.'}</p>`;
    return;
  }

  const totalPages = Math.max(1, Math.ceil(total / kidSearchPageSize));
  currentKidSearchPage = Math.min(Math.max(1, currentKidSearchPage), totalPages);
  const start = (currentKidSearchPage - 1) * kidSearchPageSize;
  const pageRows = kidSearchCache.slice(start, start + kidSearchPageSize);
  const end = Math.min(start + kidSearchPageSize, total);
  const filteredText = total === catalogueTotal ? '' : ` <span class="filter-note">filtered from ${catalogueTotal}</span>`;

  target.innerHTML = `
    <div class="kid-catalogue-toolbar">
      <div class="kid-catalogue-summary">Showing ${start + 1}-${end} of ${total} books${filteredText}</div>
      <div class="kid-catalogue-controls" aria-label="Catalogue pages">
        <button class="small secondary" type="button" onclick="prevKidSearchPage()" ${currentKidSearchPage <= 1 ? 'disabled' : ''}>Previous</button>
        <span id="kid-search-page-indicator">Page ${currentKidSearchPage} of ${totalPages}</span>
        <button class="small secondary" type="button" onclick="nextKidSearchPage()" ${currentKidSearchPage >= totalPages ? 'disabled' : ''}>Next</button>
        <select id="kid-search-page-size" aria-label="Books per page" onchange="changeKidSearchPageSize()">
          <option value="10" ${kidSearchPageSize === 10 ? 'selected' : ''}>10 / page</option>
          <option value="25" ${kidSearchPageSize === 25 ? 'selected' : ''}>25 / page</option>
          <option value="50" ${kidSearchPageSize === 50 ? 'selected' : ''}>50 / page</option>
        </select>
      </div>
    </div>
    <div class="table-scroll kid-catalogue-scroll">
      <table id="kid-search-table" class="kid-catalogue-table">
        <tr><th>Cover</th><th>Book</th><th>Author / Illustrator</th><th>Shelf</th><th>Copies</th><th>Status</th></tr>
        ${pageRows.map((r, idx) => renderKidSearchRow(r, start + idx)).join('')}
      </table>
    </div>
  `;
}

function renderKidSearchRow(r, index) {
  const shelf = r.shelf_location || r.category || 'Ask a grown-up';
  const copies = r.owned_qty || 1;
  return `<tr class="kid-catalogue-row">
    <td data-label="Cover">${coverImg(r, 'kid-table-cover')}</td>
    <td data-label="Book">
      <button class="kid-table-title-button" type="button" onclick="showBookModal(${index})">
        <strong>${escapeHtml(r.title)}</strong>
      </button>
      ${r.synopsis ? `<div class="kid-table-synopsis">${escapeHtml(r.synopsis)}</div>` : ''}
      ${r.condition_note ? `<div class="condition-note">Note: ${escapeHtml(r.condition_note)}</div>` : ''}
    </td>
    <td data-label="Author / Illustrator">${escapeHtml(r.author)}${r.illustrator ? '<br><small>Illus. ' + escapeHtml(r.illustrator) + '</small>' : ''}</td>
    <td data-label="Shelf">${escapeHtml(shelf)}</td>
    <td data-label="Copies">${escapeHtml(copies)}</td>
    <td data-label="Status">${statusBadge(r)}</td>
  </tr>`;
}

function prevKidSearchPage() {
  currentKidSearchPage -= 1;
  renderKidSearchPage();
}

function nextKidSearchPage() {
  currentKidSearchPage += 1;
  renderKidSearchPage();
}

function changeKidSearchPageSize() {
  kidSearchPageSize = Number(document.getElementById('kid-search-page-size')?.value || 10);
  currentKidSearchPage = 1;
  renderKidSearchPage();
}

function jsString(value) {
  return escapeHtml(JSON.stringify(String(value ?? '')));
}

function canQuickBorrowBook(book) {
  if (!book) return false;
  if ((book.condition_status || 'good') === 'damaged_needs_repair') return false;
  return (book.status || 'available') !== 'borrowed';
}

function ensureQuickBorrowStyles() {
  if (document.getElementById('quick-borrow-styles')) return;
  const style = document.createElement('style');
  style.id = 'quick-borrow-styles';
  style.textContent = `
    .quick-borrow-toggle {
      width: 100%;
      margin-top: 16px;
      padding: 18px;
      border-radius: 18px;
      background: #37b24d;
      font-size: 22px;
    }
    .quick-borrow-panel {
      margin-top: 16px;
      padding: 16px;
      border: 4px solid #c0eb75;
      border-radius: 22px;
      background: white;
    }
    .quick-borrow-panel[hidden] { display: none; }
    .quick-borrow-panel h3 {
      margin: 0 0 6px;
      font-size: 24px;
    }
    .quick-borrow-help {
      margin: 0 0 12px;
      font-weight: 800;
      color: #334155;
    }
    .quick-borrow-readers {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(105px, 1fr));
      gap: 10px;
      margin: 10px 0 12px;
    }
    .quick-borrow-reader.selected {
      border-color: #37b24d;
      background: #ebfbee;
      box-shadow: 0 0 0 4px rgba(55, 178, 77, .18);
    }
    .quick-borrow-scan summary {
      cursor: pointer;
      font-size: 18px;
      font-weight: 900;
      margin: 8px 0;
    }
    .quick-borrow-submit {
      width: 100%;
      margin-top: 14px;
      padding: 16px;
      border-radius: 18px;
      background: #f76707;
      font-size: 20px;
    }
    .quick-borrow-book-code {
      display: inline-block;
      margin-top: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      background: #f1f5f9;
      color: #334155;
      font-weight: 900;
    }
    @media (max-width: 700px) {
      .quick-borrow-readers { grid-template-columns: repeat(auto-fill, minmax(92px, 1fr)); }
      .quick-borrow-toggle, .quick-borrow-submit { font-size: 19px; }
    }
  `;
  document.head.appendChild(style);
}

function quickBorrowReadersHtml() {
  if (!childrenCache.length) return '<p class="kid-hint">No children are set up yet. Add a child in Admin first.</p>';
  return childrenCache.map(child => `
    <button class="reader-picker quick-borrow-reader" data-barcode="${escapeHtml(child.barcode)}" type="button" onclick="selectQuickBorrowChild(${jsString(child.barcode)})" aria-label="Choose ${escapeHtml(child.name)}">
      ${childPhoto(child, 'reader-photo')}
      <span>${escapeHtml(child.name)}</span>
      <small>${escapeHtml(child.active_loans ?? 0)}/${escapeHtml(child.borrow_limit ?? '')}</small>
    </button>
  `).join('');
}

function openQuickBorrowPanel() {
  const panel = document.getElementById('quick-borrow-panel');
  if (!panel) return;
  panel.hidden = false;
  panel.innerHTML = `
    <h3>Who is borrowing this?</h3>
    <p class="quick-borrow-help">Tap a reader, or scan their library card.</p>
    <input id="quick-borrow-child-select" type="hidden" />
    <div class="quick-borrow-readers">${quickBorrowReadersHtml()}</div>
    <details class="quick-borrow-scan">
      <summary>Scan a library card instead</summary>
      <div class="scan-input-row">
        <input id="quick-borrow-child-scan" class="kid-input kid-card-scan" placeholder="Scan library card" autocomplete="off" />
        <button class="scan-button" type="button" title="Scan with camera" onclick="openBarcodeScanner('quick-borrow-child-scan', submitQuickBorrow)">📷</button>
      </div>
    </details>
    <button class="quick-borrow-submit" type="button" onclick="submitQuickBorrow()">Borrow this book</button>
    <p id="quick-borrow-result" class="result kid-result"></p>
  `;

  const scan = document.getElementById('quick-borrow-child-scan');
  if (scan) {
    scan.addEventListener('input', () => {
      const selected = document.getElementById('quick-borrow-child-select');
      if (scan.value.trim() && selected) selected.value = '';
      renderQuickBorrowSelection();
    });
    scan.addEventListener('keydown', e => {
      if (e.key === 'Enter') submitQuickBorrow();
    });
  }

  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function selectQuickBorrowChild(barcode) {
  const selected = document.getElementById('quick-borrow-child-select');
  const scan = document.getElementById('quick-borrow-child-scan');
  if (selected) selected.value = barcode;
  if (scan) scan.value = '';
  renderQuickBorrowSelection();
}

function renderQuickBorrowSelection() {
  const selected = document.getElementById('quick-borrow-child-select')?.value?.trim() || '';
  document.querySelectorAll('.quick-borrow-reader').forEach(btn => {
    btn.classList.toggle('selected', Boolean(selected) && btn.dataset.barcode === selected);
  });
}

function selectedQuickBorrowChildBarcode() {
  const scanned = document.getElementById('quick-borrow-child-scan')?.value?.trim() || '';
  const selected = document.getElementById('quick-borrow-child-select')?.value?.trim() || '';
  return scanned || selected;
}

async function submitQuickBorrow() {
  const resultId = 'quick-borrow-result';
  const childBarcode = selectedQuickBorrowChildBarcode();
  if (!quickBorrowBookCode) return setResult(resultId, 'This book does not have a barcode to borrow.', false);
  if (!childBarcode) return setResult(resultId, 'Choose a reader or scan a library card first.', false);

  try {
    const r = await api('/api/checkout', {
      method: 'POST',
      body: JSON.stringify({ child_barcode: childBarcode, book_code: quickBorrowBookCode })
    });
    const message = `🎉 ${r.child} borrowed “${r.title}”. Bring it back by ${r.due_at}.`;
    setResult(resultId, message);
    setResult('borrow-result', message);
    quickBorrowBookCode = '';
    document.querySelector('.quick-borrow-submit')?.setAttribute('disabled', 'disabled');
    await refreshAll();
  } catch (e) {
    setResult(resultId, e.message, false);
  }
}

function showBookModal(index) {
  const r = kidSearchCache[index];
  if (!r) return;
  ensureQuickBorrowStyles();

  const status = kidStatusText(r);
  const canBorrow = canQuickBorrowBook(r);
  const bookCode = r.barcode || r.isbn || '';
  quickBorrowBookCode = bookCode;

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
        ${bookCode ? `<div class="quick-borrow-book-code">Book code: ${escapeHtml(bookCode)}</div>` : ''}
        ${r.synopsis ? `<p class="modal-synopsis">${escapeHtml(r.synopsis)}</p>` : '<p class="modal-synopsis">No story blurb yet.</p>'}
        ${canBorrow && bookCode
          ? `<button class="quick-borrow-toggle" type="button" onclick="openQuickBorrowPanel()">⚡ Quick Borrow</button>
             <div id="quick-borrow-panel" class="quick-borrow-panel" hidden></div>`
          : `<div class="modal-action-note">${canBorrow ? 'Ask a grown-up to add a barcode before borrowing this one.' : 'Ask a grown-up about this one.'}</div>`}
      </div>
    </div>
  `;
  document.getElementById('book-modal').hidden = false;
}

async function refreshBooks() {
  ensureAdminFilterControls();
  const rows = await api('/api/books');
  booksCache = filterBookRows(rows, getAdminBookFilters());
  currentBookPage = 1;
  renderBooksPage();
}

function clearBookSearch() {
  const search = document.getElementById('book-search');
  if (search) search.value = '';
  const field = document.getElementById('book-search-field');
  if (field) field.value = 'all';
  const status = document.getElementById('book-status-filter');
  if (status) status.value = 'all';
  currentBookPage = 1;
  refreshBooks();
}

async function refreshAll() {
  try {
    await Promise.all([refreshChildren(), refreshBooks(), refreshLoans()]);
    kidCatalogueRows = [];
    await kidSearchBooks({ forceReload: true });
  } catch (e) {
    console.error(e);
  }
}

function setupCatalogueFilters() {
  ensureKidFilterControls();
  ensureAdminFilterControls();

  const kidInput = document.getElementById('kid-search');
  if (kidInput && !kidInput.dataset.catalogueFilterBound) {
    kidInput.dataset.catalogueFilterBound = 'true';
    let timer;
    kidInput.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => kidSearchBooks(), 250);
    });
  }
}

window.addEventListener('load', () => {
  setupCatalogueFilters();
  kidSearchBooks();
});