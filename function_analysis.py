"""函数识别与长度汇总：给代码统计提供「函数个数 / 最大 / 最小 / 均值 / 中位数」。

Python 用标准库 ast（能拿到装饰器行号与嵌套函数）；
C、C++、Java、C# 用 Tree-sitter 语法树，只认真正带函数体的定义，
不把声明、调用和匿名 lambda 算进去。解析失败时返回 None，
由调用方标注「函数指标可能不完整」，而不是伪装成 0 个函数。
"""
import ast
import importlib
from functools import lru_cache
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
    - ``(None, 提示)``：语言不支持或解析器不可用。
    """
    if language not in TARGET_LANGUAGES:
        return None, '该语言暂未提供函数统计'
    if language == 'Python':
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

    # 其他语言：用 Tree-sitter 遍历语法树。
    try:
        from tree_sitter import Parser

        tree = Parser(grammar_for(language)).parse(source.encode('utf-8'))
    except (ImportError, ValueError, RuntimeError, MemoryError):
        return None, '函数语法解析器不可用，请重新安装 requirements.txt 中的依赖'

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
