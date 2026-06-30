let currentKidSearchPage = 1;
let kidSearchPageSize = 10;
let lastKidSearchQuery = '';
let kidCatalogueRows = [];

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
