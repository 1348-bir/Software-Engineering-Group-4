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

/** Share polling state and DOM updates; pages supply their row and stat formats. */
function createHistoryPoller({url, latestId, renderRow, stats}) {
    let inFlight = false;
    return async function () {
        if (inFlight) return;
        inFlight = true;
        try {
            const res = await fetch(url + '?after=' + latestId);
            const data = await res.json();
            if (data.attempts.length > 0) {
                const tbody = document.getElementById('historyBody');
                if (tbody.querySelector('.empty-tip')) tbody.textContent = '';
                data.attempts.forEach(attempt => {
                    const row = document.createElement('tr');
                    renderRow(row, attempt);
                    tbody.insertBefore(row, tbody.firstChild);
                });
                latestId = data.latest_id;
            }
            Object.entries(stats).forEach(([id, format]) => {
                document.getElementById(id).textContent = format(data.stats);
            });
        } catch (error) {
            console.error('poll failed', error);
        } finally {
            inFlight = false;
        }
    };
}
