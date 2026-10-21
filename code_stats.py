"""Count physical source lines using Pygments language-aware tokenization."""
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

MAX_UPLOAD = 1024 * 1024 * 1024
MAX_FILE = MAX_UPLOAD
MAX_TOTAL = MAX_UPLOAD
# Allow multipart boundaries/headers in addition to the 1 GB of actual files.
MAX_REQUEST = MAX_UPLOAD + 4 * 1024 * 1024
READ_CHUNK = 1024 * 1024
MAX_FILES = 1000
IGNORED = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.idea', 'dist', 'build', '__MACOSX'}
FIELDS = ('total', 'code', 'comment', 'blank', 'comment_any')


def stream_size(stream):
    position = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(position)
    return size


def read_source(stream):
    stream.seek(0)
    utf16 = stream.read(2) in (b'\xff\xfe', b'\xfe\xff')
    for encoding in (('utf-16',) if utf16 else ('utf-8-sig', 'gb18030')):
        try:
            stream.seek(0)
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
                output.write(decoder.decode(b'', final=True))
                return output.getvalue(), size
        except UnicodeDecodeError:
            pass
    raise ValueError('无法识别文件编码，请转换为 UTF-8')


def count_source(name, data):
    if len(data) > MAX_FILE:
        raise ValueError('单文件超过 1 GB')
    return count_stream(name, BytesIO(data), len(data))


def count_stream(name, stream, size):
    if size > MAX_FILE:
        raise ValueError('单文件超过 1 GB')
    source, actual_size = read_source(stream)
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
    boundaries = {point for start, end in (function_ranges or []) for point in (start - 1, end)}
    code_prefix = {0: 0}
    result = dict(name=name, language=lexer.name, total=total, code=0, comment=0,
                  blank=0, comment_any=0, bytes=actual_size)
    has_code = has_comment = False
    processed = 0

    def finish_line():
        nonlocal has_code, has_comment, processed
        if processed < total:
            result['code' if has_code else 'comment' if has_comment else 'blank'] += 1
            result['comment_any'] += int(has_comment)
            processed += 1
            if processed in boundaries:
                code_prefix[processed] = result['code']
        has_code = has_comment = False

    for token, value in lex(source, lexer):
        # Preprocessor directives (#include, #define) are source, not comments.
        is_comment = token in Comment and token not in Comment.Preproc and token not in Comment.PreprocFile
        # Keep only the current line's flags instead of per-line lists for GB-scale input.
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
        finish_line()
    lengths = [code_prefix[end] - code_prefix[start - 1] for start, end in (function_ranges or [])]
    result.update(summarize_lengths(lengths))
    result['function_supported'] = function_ranges is not None
    result['function_warning'] = function_warning
    result['_function_lengths'] = lengths
    if function_ranges is None:
        result['functions'] = None
    return result


def analyze_uploads(uploads):
    if sum(stream_size(upload.stream) for upload in uploads) > MAX_UPLOAD:
        raise ValueError('上传文件总大小超过 1 GB，请分批统计')
    results, skipped = [], []
    seen = set()
    total_bytes, attempted = 0, 0

    def consume(name, stream, size):
        nonlocal total_bytes, attempted
        name = name.replace('\\', '/')
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or any(p in IGNORED for p in path.parts):
            skipped.append({'name': name, 'reason': '忽略的目录或非法路径'})
            return
        attempted += 1
        if attempted > MAX_FILES:
            raise ValueError('最多统计 1000 个文件，请缩小选择范围')
        total_bytes += size
        if total_bytes > MAX_TOTAL:
            raise ValueError('文件解压后的总大小超过 1 GB')
        if name in seen:
            skipped.append({'name': name, 'reason': '重复文件路径'})
            return
        seen.add(name)
        try:
            results.append(count_stream(name, stream, size))
        except (ValueError, UnicodeError) as exc:
            skipped.append({'name': name, 'reason': str(exc)})

    for upload in uploads:
        name = upload.filename or 'unnamed'
        if name.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(upload.stream) as archive:
                    infos = archive.infolist()
                    if len(infos) > MAX_FILES:
                        raise ValueError('ZIP 中条目超过 1000 个')
                    for info in infos:
                        if info.is_dir():
                            continue
                        entry = name + '/' + info.filename
                        if info.file_size > MAX_FILE:
                            skipped.append({'name': entry, 'reason': '单文件超过 1 GB'})
                            continue
                        if total_bytes + info.file_size > MAX_TOTAL:
                            raise ValueError('文件解压后的总大小超过 1 GB')
                        if info.flag_bits & 1:
                            skipped.append({'name': entry, 'reason': '加密 ZIP 条目无法读取'})
                            continue
                        with archive.open(info) as member:
                            consume(entry, member, info.file_size)
            except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:
                raise ValueError('ZIP 损坏、加密或压缩格式不受支持') from exc
        else:
            consume(name, upload.stream, stream_size(upload.stream))

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
        function_lengths[row['language']].extend(row.pop('_function_lengths'))
        if row['function_warning'] and row['language'] in TARGET_LANGUAGES:
            function_incomplete[row['language']] += 1
    language_summary = []
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
            'languages': [{'language': key, **value} for key, value in sorted(languages.items(), key=lambda pair: -pair[1]['code'])]}
