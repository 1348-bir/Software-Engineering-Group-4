"""函数识别与长度汇总：给代码统计提供「函数个数 / 最大 / 最小 / 均值 / 中位数」。

Python 用标准库 ast（能拿到装饰器行号与嵌套函数）；
C、C++、Java、C# 用 Tree-sitter 语法树，只认真正带函数体的定义，
不把声明、调用和匿名 lambda 算进去。解析失败时返回 None，
由调用方标注「函数指标可能不完整」，而不是伪装成 0 个函数。

Tree-sitter 是原生扩展，某些输入下会直接触发访问冲突（0xC0000005），
把整个 Flask 进程带走。因此非 Python 语言的解析放在**常驻子进程**里执行：
子进程崩了只会让当前文件的函数指标缺失，网站本身继续服务；
同时子进程复用，避免每个文件都重新启动解释器（大项目才不会统计几分钟）。
"""
import ast
import atexit
import importlib
import json
import queue
import subprocess
import sys
import threading
from functools import lru_cache
from pathlib import Path
from statistics import mean, median

# 固定支持的五种语言，其余语言只统计行数。
TARGET_LANGUAGES = ('C', 'C++', 'Java', 'Python', 'C#')
GRAMMARS = {'C': 'tree_sitter_c', 'C++': 'tree_sitter_cpp',
            'Java': 'tree_sitter_java', 'C#': 'tree_sitter_c_sharp'}
# 各语言语法树里代表「函数定义」的节点类型。
FUNCTION_NODES = {
    'C': {'function_definition'},
    'C++': {'function_definition'},
    'Java': {'method_declaration', 'constructor_declaration', 'compact_constructor_declaration'},
    'C#': {'method_declaration', 'constructor_declaration', 'destructor_declaration',
           'local_function_statement', 'operator_declaration', 'conversion_operator_declaration'},
}

# Tree-sitter 子进程的入口脚本与单文件超时时间。
WORKER = Path(__file__).resolve().parent / 'function_worker.py'
WORKER_TIMEOUT = 60
# 超大源码即使不崩也会卡住很久，直接跳过函数指标（行数统计不受影响）。
MAX_TS_SOURCE = 4 * 1024 * 1024
# 子进程内仍单线程解析；这里保留锁，防止有人在同进程里直接调用。
_TS_LOCK = threading.Lock()


class _Worker:
    """常驻的 Tree-sitter 解析子进程。

    一次启动、反复复用；子进程意外退出（例如原生崩溃）时，
    当前文件返回失败提示，下一次调用会自动重启子进程。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._process = None
        self._responses = None

    def _spawn(self):
        # 使用带缓冲的管道：bufsize=0 时大 payload 的 write 可能只写入一部分，
        # 子进程会一直等剩余字节，表现为几十秒的假死。
        self._process = subprocess.Popen(
            [sys.executable, str(WORKER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=str(WORKER.parent))
        self._responses = queue.Queue()
        threading.Thread(target=self._pump, args=(self._process.stdout, self._responses),
                         daemon=True).start()

    @staticmethod
    def _pump(stream, responses):
        """把子进程的每行 JSON 结果放进队列；进程结束时放 None 唤醒等待者。"""
        try:
            for line in iter(stream.readline, b''):
                responses.put(line)
        except (OSError, ValueError):
            pass
        finally:
            responses.put(None)

    def _close(self):
        process, self._process, self._responses = self._process, None, None
        if process is None:
            return
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass

    def parse(self, language, source):
        """解析一个文件；失败返回 None（调用方给出提示并继续处理其他文件）。"""
        payload = json.dumps({'language': language, 'source': source}).encode('utf-8') + b'\n'
        with self._lock:
            for attempt in range(2):
                try:
                    if self._process is None or self._process.poll() is not None:
                        self._spawn()
                    self._process.stdin.write(payload)
                    self._process.stdin.flush()
                    line = self._responses.get(timeout=WORKER_TIMEOUT)
                    if line is None:
                        raise BrokenPipeError('worker exited')
                    return json.loads(line.decode('utf-8'))
                except queue.Empty:
                    self._close()
                    return None
                except (BrokenPipeError, OSError, ValueError):
                    self._close()
                    if attempt:
                        return None
        return None


_CLIENT = _Worker()
atexit.register(_CLIENT._close)


@lru_cache(maxsize=4)
def grammar_for(language):
    """加载并缓存 Tree-sitter 语法对象；每种语言只构造一次。"""
    from tree_sitter import Language

    return Language(importlib.import_module(GRAMMARS[language]).language())


def find_functions(source, language):
    """返回函数定义的 1 基闭区间列表，以及一条完整性提示。

    返回值有三种形态：
    - ``(ranges, None)``：识别成功；
    - ``(ranges, 提示)``：识别成功但源码存在语法错误；
    - ``(None, 提示)``：语言不支持、解析器不可用或子进程崩溃。
    """
    if language not in TARGET_LANGUAGES:
        return None, '该语言暂未提供函数统计'
    if language == 'Python':
        return _parse_python(source)
    return _parse_isolated(source, language)


def _parse_python(source):
    """Python 走标准库 ast，不涉及原生扩展，进程内直接解析。"""
    try:
        root = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None, 'Python 语法不完整或解析失败，未计算函数指标'
    ranges = []
    for node in ast.walk(root):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 起始行取「装饰器行」与 def 行的较小者，长度才包含装饰器。
            start = min([node.lineno] + [decorator.lineno for decorator in node.decorator_list])
            ranges.append((start, node.end_lineno))
    return ranges, None


def _parse_isolated(source, language):
    """通过常驻子进程解析 C/C++/Java/C#；崩溃或超时只影响当前文件。"""
    if len(source) > MAX_TS_SOURCE:
        return None, '文件较大（超过 4 MB），未计算函数指标'
    result = _CLIENT.parse(language, source)
    if not isinstance(result, dict):
        return None, '函数解析器异常，已跳过该文件的函数指标'
    ranges = result.get('ranges')
    warning = result.get('warning')
    if ranges is not None:
        # 原生解析器偶尔会返回越界位置（例如几亿行），这类结果一律视为不可信。
        line_count = source.count('\n') + 1
        cleaned = []
        for item in ranges:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                return None, '函数位置解析异常，已忽略该文件的函数指标'
            start, end = int(item[0]), int(item[1])
            if not 1 <= start <= end <= line_count:
                return None, '函数位置解析异常，已忽略该文件的函数指标'
            cleaned.append((start, end))
        ranges = cleaned
    return ranges, warning


def _parse_in_process(source, language):
    """真正的 Tree-sitter 解析（只在子进程里调用）。

    独立出来是为了让子进程可以直接复用，而不必再次 fork 子进程。
    """
    from tree_sitter import Parser

    with _TS_LOCK:
        # parser 保持存活到遍历结束，避免原生对象提前释放。
        parser = Parser(grammar_for(language))
        tree = parser.parse(source.encode('utf-8'))

        ranges = []
        cursor = tree.walk()
        while True:
            node = cursor.node
            if node.type in FUNCTION_NODES[language]:
                body = node.child_by_field_name('body')
                # C# 的表达式体成员没有 body 字段，改用箭头/构造体/代码块判断。
                has_body = body is not None or any(
                    child.type in ('arrow_expression_clause', 'constructor_body', 'block')
                    for child in node.named_children)
                if has_body:
                    end = node.end_point.row + int(node.end_point.column > 0)
                    ranges.append((node.start_point.row + 1, end))
            # 深度优先遍历：先下钻子节点，再依次访问兄弟，最后回退并结束。
            if cursor.goto_first_child():
                continue
            while not cursor.goto_next_sibling():
                if not cursor.goto_parent():
                    warning = '源码存在语法错误，函数指标可能不完整' if tree.root_node.has_error else None
                    return ranges, warning


def summarize_lengths(lengths):
    """由函数长度列表算出个数、最大/最小/均值/中位数；空列表时指标为 None。"""
    return {
        'functions': len(lengths),
        'function_max': max(lengths) if lengths else None,
        'function_min': min(lengths) if lengths else None,
        'function_mean': round(mean(lengths), 2) if lengths else None,
        'function_median': round(median(lengths), 2) if lengths else None,
    }
