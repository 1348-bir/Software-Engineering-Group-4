"""Convert spoken Chinese arithmetic into expressions for user confirmation."""
import re
import unicodedata
from common.arithmetic import solve

NUMBERS = '零〇一二两三四五六七八九十百千幺'


def number(text):
    digits = dict(zip('零一二三四五六七八九', range(10)))
    digits.update({'两':2,'〇':0,'幺':1})
    if not any(x in text for x in '十百千'):
        return ''.join(x if x.isascii() and x.isdigit() else str(digits[x]) for x in text)
    if re.search(r'[百千][一二两三四五六七八九幺0-9]$', text):
        raise ValueError('百千后的省略读法有歧义，请说完整位数')
    total, current = 0, 0
    for char in re.findall(r'\d+|.', text):
        if char.isascii() and char.isdigit():
            current = int(char)
        elif char in digits:
            current = digits[char]
        else:
            total += (current or 1) * {'十':10,'百':100,'千':1000}[char]
            current = 0
    return str(total + current)


def parse_spoken(text):
    if not isinstance(text, str) or len(text) > 10000:
        raise ValueError('语音文字过长或格式错误')
    text = unicodedata.normalize('NFKC',text)
    # Speech services can finalize a fragment in the middle of one expression.
    text = re.sub(r'(?<=[加减乘除以+×÷(])\s*[\n，,。]\s*', '', text)
    text = re.sub(r'\s*[\n，,。]\s*(?=(?:加上|减去|乘以|除以|加|减|乘|除|[+×÷]))', '', text)
    text = re.sub(r'第[0-9'+NUMBERS+r']+题', '\n', text)
    chunks = re.split(r'[\n。；;，,]|下一题|然后', text)
    questions, rejected = [], []
    for raw in chunks:
        raw = raw.strip()
        if not raw:
            continue
        expr = re.sub(r'^(请问|请计算|计算一下|计算)', '', raw)
        expr = re.sub(r'^\s*\d+[、:：]\s*','',expr)
        expr = re.sub(r'(等于多少|等于几|是多少|得多少|等于|=).*$', '', expr)
        expr = expr.replace('左括号','(').replace('右括号',')').replace('括号开','(').replace('括号关',')')
        try:
            expr = re.sub('[0-9'+NUMBERS+']+', lambda m:number(m.group()), expr)
        except ValueError:
            rejected.append(raw)
            continue
        for source, target in [('乘以','×'),('乘上','×'),('除以','÷'),('加上','+'),('减去','-'),('减掉','-'),('加','+'),('减','-'),('乘','×'),('除','÷'),('负','-'),('点','.'),('*','×'),('/','÷')]:
            expr = expr.replace(source,target)
        expr = re.sub(r'[\s?！!]', '', expr)
        if len(expr) <= 512 and re.search(r'[+\-×÷]',expr) and solve(expr)[0]:
            questions.append({'expr':expr,'spoken':raw})
        else:
            rejected.append(raw)
        if len(questions)>200:
            raise ValueError('每次最多 200 道题，请分批说题')
    return {'questions':questions,'count':len(questions),'unrecognized':rejected}
