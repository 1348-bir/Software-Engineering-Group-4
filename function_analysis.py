"""Find named function definitions; sizes are measured using the code-line counter."""
import ast
import importlib
from functools import lru_cache
from statistics import mean, median

TARGET_LANGUAGES = ('C', 'C++', 'Java', 'Python', 'C#')
GRAMMARS = {'C': 'tree_sitter_c', 'C++': 'tree_sitter_cpp', 'Java': 'tree_sitter_java', 'C#': 'tree_sitter_c_sharp'}
FUNCTION_NODES = {
    'C': {'function_definition'},
    'C++': {'function_definition'},
    'Java': {'method_declaration', 'constructor_declaration', 'compact_constructor_declaration'},
    'C#': {'method_declaration', 'constructor_declaration', 'destructor_declaration', 'local_function_statement', 'operator_declaration', 'conversion_operator_declaration'},
}


@lru_cache(maxsize=4)
def grammar_for(language):
    from tree_sitter import Language
    return Language(importlib.import_module(GRAMMARS[language]).language())


def find_functions(source, language):
    """Return inclusive, 1-based source ranges and a completeness notice."""
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
                start = min([node.lineno] + [decorator.lineno for decorator in node.decorator_list])
                ranges.append((start, node.end_lineno))
        return ranges, None
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
            # C# expression-bodied members, including local functions.
            has_body = body is not None or any(child.type in ('arrow_expression_clause', 'constructor_body', 'block') for child in node.named_children)
            if has_body:
                end = node.end_point.row + int(node.end_point.column > 0)
                ranges.append((node.start_point.row + 1, end))
        if cursor.goto_first_child():
            continue
        while not cursor.goto_next_sibling():
            if not cursor.goto_parent():
                warning = '源码存在语法错误，函数指标可能不完整' if tree.root_node.has_error else None
                return ranges, warning


def summarize_lengths(lengths):
    return {
        'functions': len(lengths),
        'function_max': max(lengths) if lengths else None,
        'function_min': min(lengths) if lengths else None,
        'function_mean': round(mean(lengths), 2) if lengths else None,
        'function_median': round(median(lengths), 2) if lengths else None,
    }
