# math_practice/ocr.py
"""可选的图片算式识别。

依赖 PaddleOCR；没安装时 ``recognize()`` 返回空字符串，
前端自动降级为手动输入，不影响其他功能。

OCR 结果通常很脏（全角符号、乘号写成 x、末尾带「= 24」），
``normalize()`` 负责把它清洗成表达式引擎能接受的写法。
"""
import re
import unicodedata
from importlib.metadata import version

_ocr = None          # PaddleOCR 实例缓存（首次识别时创建）
_available = None    # 依赖是否可用的缓存：None=未检测，True/False=已检测


def _check_available():
    """检测 PaddleOCR 是否可导入；结果缓存，避免每次请求都 try-import。"""
    global _available
    if _available is not None:
        return _available
    try:
        from paddleocr import PaddleOCR  # noqa: F401  仅用于探测依赖
        _available = True
    except ImportError:
        _available = False
    return _available


def get_ocr():
    """惰性创建 PaddleOCR 实例（初始化很慢，只做一次）。"""
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        if int(version('paddleocr').split('.')[0]) >= 3:
            _ocr = PaddleOCR(lang='ch', use_doc_orientation_classify=False,
                             use_doc_unwarping=False, use_textline_orientation=True)
        else:
            _ocr = PaddleOCR(use_angle_cls=True, lang='ch')
    return _ocr


def normalize(text):
    """把 OCR 文本清洗成表达式：统一运算符、去掉等号后的答案与空白。"""
    text = unicodedata.normalize('NFKC', text)
    text = text.replace('（', '(').replace('）', ')').replace('＝', '=')
    text = text.replace('x', '×').replace('X', '×')
    text = text.replace('*', '×')
    text = text.replace('÷', '÷').replace('/', '÷')
    # 各种「横线」都当减号（OCR 容易把减号识别成全角或破折号）。
    text = text.replace('一', '-').replace('—', '-').replace('－', '-')
    text = text.replace('＋', '+')
    # 只保留数字与运算符，其他字符一律丢弃。
    text = re.sub(r'[^0-9+\-×÷^()=]', '', text)
    text = re.sub(r'\s+', '', text)
    if '=' in text:
        # 图片里常写成「3+5=8」，只取等号左边的算式。
        text = text.split('=')[0]
    return text


def recognize(image_path):
    """识别图片中的算式，返回清洗后的表达式字符串；失败返回空串。"""
    if not _check_available():
        raise RuntimeError('OCR 引擎未安装。请使用 Python 3.11 或 3.12 的独立环境安装 requirements-ocr.txt 后启动应用。')
    try:
        engine = get_ocr()
        lines = []
        if callable(getattr(engine, 'predict', None)):
            for result in engine.predict(image_path):
                if not isinstance(result, dict):
                    result = result.json
                if isinstance(result, str):
                    import json
                    result = json.loads(result)
                result = result.get('res', result)
                lines.extend(result.get('rec_texts', []))
        else:
            for block in engine.ocr(image_path, cls=True) or []:
                for item in block or []:
                    lines.append(item[1][0])
        from .engine import solve
        candidates = []
        for line in lines:
            expr = normalize(line)
            if expr and solve(expr)[0]:
                candidates.append(expr)
        if len(candidates) > 1:
            raise RuntimeError('检测到多道算式，请裁剪为单道题后重试。')
        return candidates[0] if candidates else ''
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError('OCR 引擎初始化或识别失败，请检查依赖、模型下载和图片格式。') from exc
