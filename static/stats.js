'use strict';
/**
 * 代码统计页的交互脚本。
 *
 * 负责三件事：
 * 1. 选择/拖拽文件，并在前端先做一次数量与大小校验（后端还会再校验一次）；
 * 2. 调用 /api/analyze 或 /api/analyze-url，把返回的 report 渲染成表格与图表；
 * 3. 把结果导出为 CSV（带 BOM，Excel 打开中文不乱码）。
 *
 * 所有来自后端的文本都通过 textContent 写入，不使用 innerHTML，
 * 避免统计结果里的文件名等不可信内容被当成 HTML 执行。
 */
const $ = id => document.getElementById(id);

// ---- 页面状态 ----
let selected = [];          // 当前选中的文件列表
let report = null;          // 最近一次统计结果
let busy = false;           // 是否有请求正在进行（防重复提交）
let resultSource = 'files'; // 结果来源：'files' 或 'url'，决定消息显示在哪个区域

// 后端把上限写在 DOM 的 data-* 属性里，避免前后端各写一份常量。
const uploadLimit = Number($('drop-zone').dataset.uploadLimit);
const fileLimit = Number($('drop-zone').dataset.fileLimit);

/** 把字节数格式化成 KB / MB / GB，保留一位小数。 */
function formatSize(bytes) {
  const unit = bytes >= 1024 ** 3 ? 'GB' : bytes >= 1024 ** 2 ? 'MB' : 'KB';
  const divisor = unit === 'GB' ? 1024 ** 3 : unit === 'MB' ? 1024 ** 2 : 1024;
  return `${(bytes / divisor).toFixed(1)} ${unit}`;
}

/** 前端预校验：文件数、单文件大小、总大小；没问题返回空串。 */
function selectionError() {
  if (selected.length > fileLimit) return `最多选择 ${fileLimit} 个文件，请分批统计。`;
  if (selected.some(f => f.size > uploadLimit)) return '单文件超过 1 GB，请缩小文件范围。';
  if (selected.reduce((sum, f) => sum + f.size, 0) > uploadLimit) return '文件总大小超过 1 GB，请分批统计。';
  return '';
}

/** 在「文件区」或「网址区」显示一条提示；text 为空时隐藏该区域。 */
function showMessage(text, error = false) {
  const target = $(resultSource === 'url' ? 'url-message' : 'message');
  target.textContent = text;
  target.className = 'message' + (error ? ' error' : '');
  target.hidden = !text;
}

/** 更新当前选择：刷新标签、按钮可用性，并清掉上一次的结果。 */
function updateSelection(files) {
  if (busy) return;
  resultSource = 'files';
  $('url-message').hidden = true;
  selected = Array.from(files);
  $('selected-label').textContent = selected.length ? `已选择 ${selected.length} 个文件 · ${formatSize(selected.reduce((sum, f) => sum + f.size, 0))}` : '尚未选择文件';
  const error = selectionError();
  $('analyze').disabled = !selected.length || busy || Boolean(error);
  $('results').hidden = true;
  report = null;
  showMessage(error, Boolean(error));
}

/** 创建元素的小工具：设置文本与类名后返回节点。 */
function make(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

/** 渲染文件明细表，支持按文件名/语言过滤；没有结果时显示占位行。 */
function renderRows() {
  const search = $('filter').value.toLowerCase();
  const rows = report.files.filter(f => `${f.name} ${f.language}`.toLowerCase().includes(search));
  $('file-rows').replaceChildren();
  for (const file of rows) {
    const row = make('tr');
    const name = make('td', file.name);
    name.append(make('small', file.language));
    row.append(name);
    for (const key of ['total', 'code', 'comment', 'blank', 'comment_any']) row.append(make('td', file[key].toLocaleString()));
    $('file-rows').append(row);
  }
  if (!rows.length) {
    const row = make('tr'), cell = make('td', '没有符合条件的代码文件');
    cell.colSpan = 6;
    row.append(cell); $('file-rows').append(row);
  }
}

/** 函数指标格式化：不支持/为空显示 "—"，解析不完整的语言加星号提示。 */
function functionValue(row, key) {
  if (!row.function_supported || row[key] === null || row[key] === undefined) return '—';
  const value = Number(row[key]).toLocaleString(undefined, { maximumFractionDigits: 2 });
  return value + (row.function_incomplete_files ? '*' : '');
}

/** 渲染按语言汇总的表格，以及「函数指标可能不完整」的提示列表。 */
function renderLanguageSummary() {
  $('language-summary-rows').replaceChildren();
  for (const language of report.language_summary || []) {
    const row = make('tr');
    for (const key of ['language', 'files', 'code', 'blank', 'comment']) row.append(make('td', typeof language[key] === 'number' ? language[key].toLocaleString() : language[key]));
    for (const key of ['functions', 'function_max', 'function_min', 'function_mean', 'function_median']) row.append(make('td', functionValue(language, key)));
    if (language.function_incomplete_files) row.title = `${language.function_incomplete_files} 个文件解析不完整，函数指标可能偏少`;
    $('language-summary-rows').append(row);
  }
  // 只对支持函数统计的语言提示「解析不完整」，其他语言本来就没有函数指标。
  const notices = report.files.filter(file => file.function_warning && ['C', 'C++', 'Java', 'Python', 'C#'].includes(file.language));
  $('function-notices').replaceChildren(...notices.map(file => make('li', `${file.name}：${file.function_warning}`)));
  $('function-notices-panel').hidden = !notices.length;
}

/** 渲染整份报告：指标卡、语言占比条、明细表、跳过清单与提示语。 */
function renderReport() {
  $('results').hidden = false;
  $('filter').value = '';
  $('metrics').replaceChildren();
  for (const [key, label] of [['files', '已统计文件'], ['total', '总行数'], ['code', '代码行'], ['comment', '纯注释行'], ['blank', '空行']]) {
    const metric = make('div', undefined, 'metric');
    metric.append(make('span', label), make('strong', report.totals[key].toLocaleString()));
    $('metrics').append(metric);
  }
  // 语言占比：按代码行数计算宽度，颜色从固定色板里循环取。
  $('languages').replaceChildren();
  if (!report.languages.length) $('languages').append(make('p', '暂无可统计的语言', 'muted'));
  report.languages.forEach((lang, index) => {
    const label = make('div', undefined, 'language-label');
    label.append(make('span', lang.language), make('span', `${lang.files} 个文件 · ${lang.code.toLocaleString()} 行代码`));
    const track = make('div', undefined, 'language-track'), bar = make('div', undefined, 'language-bar');
    bar.style.width = `${report.totals.code ? lang.code / report.totals.code * 100 : 0}%`;
    bar.style.backgroundColor = ['#a18adf', '#86b2c9', '#d7ac88', '#9cc1aa', '#c395b2'][index % 5];
    track.append(bar); $('languages').append(label, track);
  });
  renderRows();
  renderLanguageSummary();
  // 跳过清单：有跳过就展开提示，没有任何结果时默认展开，方便排查原因。
  $('skipped-panel').hidden = !report.skipped.length;
  $('skipped-panel').open = !report.files.length;
  $('skipped-label').textContent = `${report.skipped.length} 个文件已跳过 · 展开查看原因`;
  $('skipped-list').replaceChildren(...report.skipped.map(f => make('li', `${f.name}：${f.reason}`)));
  showMessage(report.files.length ? `统计完成：${report.totals.files} 个文件，${report.totals.comment_any} 行含有注释。` : '没有识别到可统计的代码文件，请查看跳过原因。', !report.files.length);
}

/** 提交当前选择的文件到后端统计。 */
async function analyze() {
  if (!selected.length || busy) return;
  resultSource = 'files';
  $('url-message').hidden = true;
  const error = selectionError();
  if (error) { showMessage(error, true); return; }
  busy = true;
  setBusy(true);
  $('analyze').textContent = '统计中…'; showMessage('正在识别语言并统计，请稍候…');
  try {
    const form = new FormData();
    // 文件夹上传时用 webkitRelativePath 保留相对路径，后端据此过滤目录。
    selected.forEach(file => form.append('files', file, file.webkitRelativePath || file.name));
    const response = await fetch('/api/analyze', { method: 'POST', body: form });
    let data;
    try { data = await response.json(); } catch { throw new Error('服务没有返回有效结果，请缩小文件范围后重试。'); }
    if (!response.ok) throw new Error(data.error || '统计失败');
    report = data; renderReport();
  } catch (error) { showMessage(error.message || '无法连接服务，请确认网站已启动。', true); }
  finally {
    setBusy(false);
    $('analyze').textContent = '开始统计 →';
  }
}

/** 请求期间禁用所有交互控件，避免重复提交或中途换文件。 */
function setBusy(value) {
  busy = value;
  ['analyze', 'choose-files', 'choose-folder', 'demo', 'function-demo', 'clear', 'analyze-url', 'source-url', 'file-input', 'folder-input'].forEach(id => $(id).disabled = value);
  if (!value) $('analyze').disabled = !selected.length || Boolean(selectionError());
}

// ---- 网址统计表单 ----
$('url-form').onsubmit = async event => {
  event.preventDefault();
  if (busy) return;
  resultSource = 'url';
  $('message').hidden = true;
  $('results').hidden = true;
  report = null;
  const url = $('source-url').value.trim();
  // 前端先挡掉明显不是 http/https 的输入，减少无谓请求。
  try {
    const parsed = new URL(url);
    if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error();
  } catch { showMessage('请输入完整的 HTTP 或 HTTPS 网址。', true); return; }
  setBusy(true);
  $('analyze-url').textContent = '正在获取…';
  showMessage('正在下载源码并统计，大文件或仓库可能需要较长时间，请保持页面打开…');
  try {
    const response = await fetch('/api/analyze-url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }) });
    let data;
    try { data = await response.json(); } catch { throw new Error('服务未返回有效结果，请稍后重试。'); }
    if (!response.ok) throw new Error(data.error || '网址统计失败');
    report = data;
    renderReport();
    if (report.files.length) $('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) { showMessage(error.message || '连接失败，请确认本地服务已启动。', true); }
  finally { setBusy(false); $('analyze-url').textContent = '从网址统计 →'; }
};

// ---- 文件选择与清空 ----
$('choose-files').onclick = () => $('file-input').click();
$('choose-folder').onclick = () => $('folder-input').click();
$('file-input').onchange = event => updateSelection(event.target.files);
$('folder-input').onchange = event => updateSelection(event.target.files);
$('clear').onclick = () => { $('file-input').value = ''; $('folder-input').value = ''; updateSelection([]); };
$('analyze').onclick = analyze;
// 明细过滤只在已有结果时重绘，避免空状态下报错。
$('filter').oninput = () => { if (report) renderRows(); };

// ---- 拖拽上传 ----
const drop = $('drop-zone');
drop.addEventListener('dragover', event => { event.preventDefault(); if (!busy) drop.classList.add('dragging'); });
drop.addEventListener('dragleave', () => drop.classList.remove('dragging'));
drop.addEventListener('drop', event => {
  event.preventDefault(); drop.classList.remove('dragging');
  if (busy) return;
  // 浏览器不支持读取拖入目录的文件列表，提示改用「选择文件夹」。
  const items = Array.from(event.dataTransfer.items || []);
  if (items.some(item => item.webkitGetAsEntry?.()?.isDirectory)) {
    showMessage('拖入文件夹请使用「选择文件夹」，或先压缩为 ZIP 再拖入。', true);
    return;
  }
  updateSelection(event.dataTransfer.files);
});

// ---- 内置示例：一键演示统计与函数识别 ----
$('demo').onclick = () => {
  updateSelection([
    new File(['# 学习从这里开始\nname = "hello"  # 行尾注释\n\nprint(name)\n'], 'hello.py'),
    new File(['// 一个小小的问候\nconst url = "https://example.com";\n/* 创建想法\n   让它发生 */\nconsole.log(url);\n'], 'hello.js'),
    new File(['/* 让页面更好看 */\nbody {\n  color: #7362df;\n}\n'], 'style.css')
  ]);
  analyze();
};
$('function-demo').onclick = () => {
  updateSelection([
    new File(['int add(int a, int b) {\n  // add two numbers\n  return a + b;\n}\n'], 'add.c'),
    new File(['int square(int n) {\n  return n * n;\n}\n'], 'square.cpp'),
    new File(['class Demo {\n  int twice(int n) {\n    return n * 2;\n  }\n}\n'], 'Demo.java'),
    new File(['# Python sample\ndef greet(name):\n    # a friendly greeting\n    return "Hello " + name\n\ndef add(a, b):\n    return a + b\n'], 'hello.py'),
    new File(['class Demo {\n  public int Double(int x) => x * 2;\n}\n'], 'Demo.cs'),
  ]);
  analyze();
};

// ---- 导出 CSV ----
$('export').onclick = () => {
  if (!report) return;
  // CSV 注入防护：以 = + - @ 等开头的单元格前加单引号；引号内部再转义。
  const safeCell = value => {
    let text = String(value);
    if (/^[=+\-@\t\r\n]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  const summary = (report.language_summary || []).map(row => [row.language, row.files, row.code, row.blank, row.comment, ...['functions', 'function_max', 'function_min', 'function_mean', 'function_median'].map(key => functionValue(row, key))]);
  const lines = [['按语言汇总（函数长度为有效代码行数）'], ['语言', '源文件数', '代码行数', '空行数', '注释行数', '函数个数', '最大值', '最小值', '均值', '中位数'], ...summary, [], ['文件明细'], ['文件', '语言', '总行数', '代码行', '纯注释行', '空行', '含注释行'], ...report.files.map(f => [f.name, f.language, f.total, f.code, f.comment, f.blank, f.comment_any]), ['合计', '', report.totals.total, report.totals.code, report.totals.comment, report.totals.blank, report.totals.comment_any]];
  // \uFEFF 是 BOM，让 Excel 正确识别 UTF-8；\r\n 兼容 Windows 换行。
  const csv = '\uFEFF' + lines.map(row => row.map(safeCell).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = make('a'); link.href = url; link.download = '代码统计.csv'; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

// ---- 兼容旧入口：服务端直接渲染结果时，把数据交给同一套渲染逻辑 ----
if (window.initialStats) {
  const initial = window.initialStats;
  resultSource = initial.source || 'files';
  if (initial.url) $('source-url').value = initial.url;
  if (initial.report) { report = initial.report; renderReport(); }
  else if (initial.error) showMessage(initial.error, true);
}
