"""Small arithmetic parser: four operations and parentheses only."""
import ast
import operator

OPERATIONS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def evaluate(expression):
    if len(expression) > 160:
        raise ValueError('算式过长')
    tree = ast.parse(expression, mode='eval')

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) is int and 0 <= node.value <= 999:
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATIONS:
            value = OPERATIONS[type(node.op)](visit(node.left), visit(node.right))
            if abs(value) > 1e12:
                raise ValueError('计算结果过大')
            return value
        raise ValueError('只允许加减乘除和括号')

    return visit(tree.body)
