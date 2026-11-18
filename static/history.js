/* 历史记录表格的公共小工具。 */
/**
 * 历史字段来自数据库，其中可能包含用户提交过的任意文本，
 * 因此统一用 textContent 写入，绝不用 innerHTML，避免 XSS。
 */
function appendHistoryCell(row, value, className = '') {
    const cell = document.createElement('td');
    cell.textContent = value == null ? '' : String(value);
    cell.className = className;
    row.appendChild(cell);
    return cell;
}
