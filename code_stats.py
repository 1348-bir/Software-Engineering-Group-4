"""多语言代码行统计引擎：按 Pygments 词法结果区分代码 / 注释 / 空行。

核心思路：把源文件当作文本流读入，用 Pygments 按语言分词，
再逐个 token 判断它是代码还是注释，最后按「行」归并：
一行里只要出现代码就算代码行，只有注释算注释行，什么都没有算空行；
含注释的行另外记到 comment_any（所以行尾注释会同时计入代码行和含注释行）。

函数长度不在这里算：``function_analysis`` 给出函数所在的行区间，
本模块只负责在这些区间里累计「代码行数」，作为函数长度。
"""
from collections import defaultdict
from pathlib import PurePosixPath
from io import BytesIO, StringIO, IncrementalNewlineDecoder
import codecs
import re
import zipfile

from pygments import lex
from pygments.lexers import get_lexer_for_filename, get_lexer_by_name
from pygments.token import Comment
from pygments.util import ClassNotFound
from function_analysis import TARGET_LANGUAGES, find_functions, summarize_lengths

# 单个文件、整批上传、ZIP 解压后总量的上限都是 1 GB。
MAX_UPLOAD = 1024 * 1024 * 1024
MAX_FILE = MAX_UPLOAD
MAX_TOTAL = MAX_UPLOAD
# 请求体上限在 1 GB 之外再留 4 MB，容纳 multipart 边界与头部。
MAX_REQUEST = MAX_UPLOAD + 4 * 1024 * 1024
# 分块读取的块大小：1 MB，兼顾内存占用与读取次数。
READ_CHUNK = 1024 * 1024
# 单次最多处理的文件数（上传、ZIP 条目、解压计数共用）。
MAX_FILES = 10_000
# multipart 部件数上限：文件数之外再留 200 给普通表单字段。
MAX_UPLOAD_FORM_PARTS = MAX_FILES + 200
# 这些目录里的文件直接跳过，不参与统计。
IGNORED = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.idea', 'dist', 'build', '__MACOSX'}
# 每行都要维护的计数字段。
FIELDS = ('total', 'code', 'comment', 'blank', 'comment_any')


def stream_size(stream):
    """返回文件流的总字节数，并把读取位置还原到调用前。"""
    position = stream.tell()
    stream.seek(0, 2)          # 移到末尾
    size = stream.tell()
    stream.seek(position)      # 还原，避免影响后续读取
    return size


def read_source(stream):
    """把文件流解码成文本，返回 ``(文本, 实际字节数)``。

    编码依次尝试 UTF-8（带 BOM）与 GB18030；有 UTF-16 BOM 时按 UTF-16 读。
    过程中做三件事：统计字节数、拦截超过 1 GB 的文件、用 NUL 字节识别二进制文件。
    """
    stream.seek(0)
    utf16 = stream.read(2) in (b'\xff\xfe', b'\xfe\xff')
    for encoding in (('utf-16',) if utf16 else ('utf-8-sig', 'gb18030')):
        try:
            stream.seek(0)
            # IncrementalNewlineDecoder 负责把 \r\n、\r 统一成 \n，便于按行切分。
            decoder = IncrementalNewlineDecoder(codecs.getincrementaldecoder(encoding)(), translate=True)
            size = 0
            with StringIO() as output:
                while data := stream.read(READ_CHUNK):
                    size += len(data)
                    if size > MAX_FILE:
                        raise ValueError('单文件超过 1 GB')
                    if not utf16 and b'\x00' in data:
                        raise ValueError('二进制文件，已跳过')
                    output.write(decoder.decode(data))
                output.write(decoder.decode(b'', final=True))   # 冲刷解码器缓冲区
                return output.getvalue(), size
        except UnicodeDecodeError:
            pass            # 该编码失败，换下一种
    raise ValueError('无法识别文件编码，请转换为 UTF-8')


def count_source(name, data):
    """内存字节串版本的计数入口（测试与内部复用）。"""
    if len(data) > MAX_FILE:
        raise ValueError('单文件超过 1 GB')
    return count_stream(name, BytesIO(data), len(data))


def count_stream(name, stream, size):
    """统计单个文件：返回行数、函数指标与语言等字段。

    行判定规则：
    - 一行中出现非注释 token → 代码行，同时若出现注释则计入 comment_any；
    - 只有注释 token → 注释行；
    - 什么都没有 → 空行。
    """
    if size > MAX_FILE:
        raise ValueError('单文件超过 1 GB')
    source, actual_size = read_source(stream)
    # 优先按文件名推断语言；无名文件（Dockerfile、Makefile 等）用别名兜底。
    try:
        lexer = get_lexer_for_filename(PurePosixPath(name).name, source, stripnl=False, ensurenl=False)
    except ClassNotFound:
        special = {'Dockerfile': 'docker', 'Makefile': 'make', '.gitignore': 'text', '.env': 'bash'}
        alias = special.get(PurePosixPath(name).name)
        if alias is None:
            raise ValueError('未识别的语言或非源码文件')
        lexer = get_lexer_by_name(alias, stripnl=False, ensurenl=False)

    total = source.count('\n') + int(bool(source) and not source.endswith('\n'))
    function_ranges, function_warning = find_functions(source, lexer.name)
    # 函数边界（起始行前一行为 start-1，结束行为 end），用于在扫描时记录代码行快照。
    boundaries = {point for start, end in (function_ranges or []) for point in (start - 1, end)}
    code_prefix = {0: 0}
    result = dict(name=name, language=lexer.name, total=total, code=0, comment=0,
                  blank=0, comment_any=0, bytes=actual_size)
    has_code = has_comment = False
    processed = 0

    def finish_line():
        """结束当前行：按行内标记累加计数，并在函数边界处记录累计代码行。"""
        nonlocal has_code, has_comment, processed
        if processed < total:
            result['code' if has_code else 'comment' if has_comment else 'blank'] += 1
            result['comment_any'] += int(has_comment)
            processed += 1
            if processed in boundaries:
                code_prefix[processed] = result['code']
        has_code = has_comment = False

    for token, value in lex(source, lexer):
        # 预处理指令（#include、#define）属于源码，不算注释。
        is_comment = token in Comment and token not in Comment.Preproc and token not in Comment.PreprocFile
        # 按换行切分 token：只保留「当前行」的两个布尔标记，GB 级输入也不会吃内存。
        for fragment in re.finditer(r'[^\n]+|\n', value):
            text = fragment.group()
            if text == '\n':
                finish_line()
            elif re.search(r'\S', text):
                if is_comment:
                    has_comment = True
                else:
                    has_code = True
    if processed < total:
        finish_line()       # 文件末尾没有换行时补一行

    # 函数长度 = 结束行代码数 - 起始行前一行的代码数（只数有效代码行）。
    lengths = [code_prefix[end] - code_prefix[start - 1] for start, end in (function_ranges or [])]
    result.update(summarize_lengths(lengths))
    result['function_supported'] = function_ranges is not None
    result['function_warning'] = function_warning
    result['_function_lengths'] = lengths
    if function_ranges is None:
        result['functions'] = None      # 不支持该语言时不要显示成 0 个函数
    return result


def analyze_uploads(uploads):
    """处理一批上传项（文件或 ZIP），返回汇总报告。

    报告包含：全局 totals、逐文件明细 files、跳过清单 skipped、
    按语言汇总的 language_summary，以及按代码行降序的 languages。
    """
    if len(uploads) > MAX_FILES:
        raise ValueError(f'最多上传 {MAX_FILES} 个文件，请分批统计')
    if sum(stream_size(upload.stream) for upload in uploads) > MAX_UPLOAD:
        raise ValueError('上传文件总大小超过 1 GB，请分批统计')
    results, skipped = [], []
    seen = set()
    total_bytes, attempted = 0, 0

    def consume(name, stream, size):
        """处理单个文件：校验路径、去重、累计大小，然后计数；失败记入跳过清单。"""
        nonlocal total_bytes, attempted
        name = name.replace('\\', '/')
        path = PurePosixPath(name)
        # 拒绝绝对路径、向上穿越，以及 .git、node_modules 等忽略目录。
        if path.is_absolute() or '..' in path.parts or any(p in IGNORED for p in path.parts):
            skipped.append({'name': name, 'reason': '忽略的目录或非法路径'})
            return
        attempted += 1
        if attempted > MAX_FILES:
            raise ValueError(f'最多统计 {MAX_FILES} 个文件，请缩小选择范围')
        if name in seen:
            skipped.append({'name': name, 'reason': '重复文件路径'})
            return
        total_bytes += size
        if total_bytes > MAX_TOTAL:
            raise ValueError('文件解压后的总大小超过 1 GB')
        seen.add(name)
        try:
            results.append(count_stream(name, stream, size))
        except (ValueError, UnicodeError) as exc:
            skipped.append({'name': name, 'reason': str(exc)})

    for upload in uploads:
        name = upload.filename or 'unnamed'
        if name.lower().endswith('.zip'):
            # ZIP：逐个条目检查大小、加密标记，再交给 consume 统一处理。
            try:
                with zipfile.ZipFile(upload.stream) as archive:
                    infos = archive.infolist()
                    if sum(not info.is_dir() for info in infos) > MAX_FILES:
                        raise ValueError(f'ZIP 中条目超过 {MAX_FILES} 个')
                    for info in infos:
                        if info.is_dir():
                            continue
                        entry = name + '/' + info.filename
                        if info.file_size > MAX_FILE:
                            skipped.append({'name': entry, 'reason': '单文件超过 1 GB'})
                            continue
                        if info.flag_bits & 1:
                            skipped.append({'name': entry, 'reason': '加密 ZIP 条目无法读取'})
                            continue
                        with archive.open(info) as member:
                            consume(entry, member, info.file_size)
            except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:
                raise ValueError('ZIP 损坏、加密或压缩格式不受支持') from exc
        else:
            consume(name, upload.stream, stream_size(upload.stream))

    # ---- 汇总 ----
    totals = {field: sum(row[field] for row in results) for field in FIELDS}
    totals['files'] = len(results)
    totals['skipped'] = len(skipped)
    languages = defaultdict(lambda: {'files': 0, **dict.fromkeys(FIELDS, 0)})
    function_lengths = defaultdict(list)
    function_incomplete = defaultdict(int)
    for row in results:
        group = languages[row['language']]
        group['files'] += 1
        for field in FIELDS:
            group[field] += row[field]
        # 跨文件收集函数长度，最后统一算均值/中位数（不是对文件均值再平均）。
        function_lengths[row['language']].extend(row.pop('_function_lengths'))
        if row['function_warning'] and row['language'] in TARGET_LANGUAGES:
            function_incomplete[row['language']] += 1

    language_summary = []
    # 固定先输出五种目标语言，其余语言（如有）按名称追加，保证表格顺序稳定。
    language_order = list(TARGET_LANGUAGES) + sorted(set(languages) - set(TARGET_LANGUAGES))
    for language in language_order:
        group = languages.get(language, {'files': 0, **dict.fromkeys(FIELDS, 0)})
        supported = language in TARGET_LANGUAGES
        language_summary.append({
            'language': language, **group,
            **summarize_lengths(function_lengths[language]),
            'function_supported': supported,
            'function_incomplete_files': function_incomplete[language],
        })
        if not supported:
            language_summary[-1]['functions'] = None
    return {'totals': totals, 'files': results, 'skipped': skipped,
            'language_summary': language_summary,
            'languages': [{'language': key, **value} for key, value in
                          sorted(languages.items(), key=lambda pair: -pair[1]['code'])]}
