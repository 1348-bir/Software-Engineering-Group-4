/* History fields are untrusted, including records saved before validation. */
function appendHistoryCell(row, value, className = '') {
    const cell = document.createElement('td');
    cell.textContent = value == null ? '' : String(value);
    cell.className = className;
    row.appendChild(cell);
    return cell;
}
