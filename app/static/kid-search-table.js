let currentKidSearchPage = 1;
let kidSearchPageSize = 10;
let lastKidSearchQuery = '';

function clearKidSearch() {
  const input = document.getElementById('kid-search');
  const target = document.getElementById('kid-search-results');
  if (input) input.value = '';
  kidSearchCache = [];
  currentKidSearchPage = 1;
  lastKidSearchQuery = '';
  if (target) target.innerHTML = '<p class="kid-hint">Search for a title, author, shelf, topic or story clue.</p>';
  input?.focus();
}

async function kidSearchBooks() {
  const input = document.getElementById('kid-search');
  const q = input?.value?.trim() || '';
  const target = document.getElementById('kid-search-results');
  if (!target) return;

  if (!q) {
    clearKidSearch();
    return;
  }

  try {
    target.classList.add('kid-catalogue-results');
    target.innerHTML = '<p class="kid-hint">Searching the shelves...</p>';
    const rows = await api('/api/books?q=' + encodeURIComponent(q));
    kidSearchCache = rows;
    lastKidSearchQuery = q;
    currentKidSearchPage = 1;
    renderKidSearchPage();
  } catch (e) {
    target.innerHTML = `<p class="kid-hint error">${escapeHtml(e.message)}</p>`;
  }
}

function renderKidSearchPage() {
  const target = document.getElementById('kid-search-results');
  if (!target) return;

  target.classList.add('kid-catalogue-results');

  const total = kidSearchCache.length;
  if (!total) {
    target.innerHTML = `<p class="kid-hint">No books found for “${escapeHtml(lastKidSearchQuery)}”. Try another word.</p>`;
    return;
  }

  const totalPages = Math.max(1, Math.ceil(total / kidSearchPageSize));
  currentKidSearchPage = Math.min(Math.max(1, currentKidSearchPage), totalPages);
  const start = (currentKidSearchPage - 1) * kidSearchPageSize;
  const pageRows = kidSearchCache.slice(start, start + kidSearchPageSize);
  const end = Math.min(start + kidSearchPageSize, total);

  target.innerHTML = `
    <div class="kid-catalogue-toolbar">
      <div class="kid-catalogue-summary">Showing ${start + 1}-${end} of ${total} books</div>
      <div class="kid-catalogue-controls" aria-label="Search result pages">
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

window.addEventListener('load', () => {
  const input = document.getElementById('kid-search');
  if (!input) return;

  let timer;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (input.value.trim()) kidSearchBooks();
      else clearKidSearch();
    }, 300);
  });

  const target = document.getElementById('kid-search-results');
  if (target && !target.innerHTML.trim()) {
    target.innerHTML = '<p class="kid-hint">Search for a title, author, shelf, topic or story clue.</p>';
  }
});
