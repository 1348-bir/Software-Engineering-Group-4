# math_practice/ocr.py
"""
OCR 识别算式。依赖 PaddleOCR（可选）。
没装时，recognize() 返回空字符串，前端降级为手动输入。
"""
import re

_ocr = None
_available = None


def _check_available():
    global _available
    if _available is not None:
        return _available
    try:
        from paddleocr import PaddleOCR  # noqa
        _available = True
    except ImportError:
        _available = False
    return _available


def get_ocr():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        _ocr = PaddleOCR(use_angle_cls=True, lang='ch')
    return _ocr


def normalize(text):
    text = text.replace('x', '×').replace('X', '×')
    text = text.replace('*', '×')
    text = text.replace('÷', '÷').replace('/', '÷')
    text = text.replace('一', '-').replace('—', '-').replace('－', '-')
    text = text.replace('＋', '+')
    text = re.sub(r'[^0-9+\-×÷^()=]', '', text)
    text = re.sub(r'\s+', '', text)
    if '=' in text:
        text = text.split('=')[0]
    return text


def recognize(image_path):
    """识别图片中的算式，返回清洗后的表达式字符串"""
    if not _check_available():
        return ''
    try:
        ocr = get_ocr()
        result = ocr.ocr(image_path, cls=True)
        lines = []
        for block in result:
            if not block:
                continue
            for item in block:
                lines.append(item[1][0])
        raw = ''.join(lines)
        return normalize(raw)
    except Exception as e:
        print(f"[OCR] 识别失败: {e}")
        return ''