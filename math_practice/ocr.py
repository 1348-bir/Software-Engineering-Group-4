# math_practice/ocr.py
"""可选的图片算式识别。

依赖 PaddleOCR；没安装时 ``recognize()`` 抛错，前端自动降级为手动输入，
不影响其他功能。

速度策略：先用轻量的 PP-OCRv5 mobile 模型（约 1 秒），
未识别出有效算式时，再用 PaddleOCR 默认配置重试。
"""
import re
import json
import os
import subprocess
from pathlib import Path
import threading
import unicodedata
from importlib.metadata import version

_ocr_fast = None      # 轻量模型：速度快，绝大多数图片够用
_ocr_accurate = None  # 准确模型：只在轻量模型失败时启用
_available = None     # 依赖是否可用的缓存：None=未检测，True/False=已检测
_warmed = False       # 是否已经预热过模型
# PaddleOCR 的初始化与推理都不是线程安全的：并发点击会让两个线程同时建引擎，
# 内存翻倍并卡死进程，因此这里把整段识别串行化，用排队换取稳定。
_lock = threading.Lock()


def _check_available():
    """检测 PaddleOCR 是否可导入；结果缓存，避免每次请求都 try-import。"""
    global _available
    if _available is not None:
        return _available
    try:
        from paddleocr import PaddleOCR  # noqa: F401  仅用于探测依赖
        _available = True
    except (ImportError, OSError, RuntimeError):
        _available = False
    return _available


def _build_engine(fast):
    """创建 PaddleOCR 引擎；fast=True 用轻量模型，False 用准确模型。"""
    from paddleocr import PaddleOCR

    if int(version('paddleocr').split('.')[0]) < 3:
        return PaddleOCR(use_angle_cls=True, lang='ch')
    kwargs = dict(
        lang='ch',
        # Windows + paddlepaddle 3.x 的 oneDNN/PIR 推理路径会抛
        # ConvertPirAttribute2RuntimeAttribute，关闭 MKLDNN 走纯 CPU 内核即可。
        # 手写算式经常被 textline 方向分类器误判成 180°（整行反向），
        # 所以关闭方向分类；同时降低检测阈值，细笔画才不会漏检。
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
        text_det_thresh=0.2,
        text_det_box_thresh=0.3,
        text_det_unclip_ratio=1.8,
    )
    if fast:
        kwargs.update(text_detection_model_name='PP-OCRv5_mobile_det',
                      text_recognition_model_name='PP-OCRv5_mobile_rec')
    return PaddleOCR(**kwargs)


def get_ocr(fast=True):
    """惰性创建引擎（初始化较慢，只做一次）。"""
    global _ocr_fast, _ocr_accurate
    if fast:
        if _ocr_fast is None:
            _ocr_fast = _build_engine(True)
        return _ocr_fast
    if _ocr_accurate is None:
        _ocr_accurate = _build_engine(False)
    return _ocr_accurate


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


def _prepare(image_path, max_side=960):
    """把超大图片缩到长边 960 像素。

    移动版检测模型在 960 像素上又快又准；手机原图直接送进去会慢很多。
    缩放失败时退回原始路径，让 PaddleOCR 自己处理，不影响正常图片。
    """
    try:
        import numpy as np
        from PIL import Image, ImageOps
    except ImportError:
        return image_path
    try:
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            if max_side > 960 and max(img.size) < 800:
                # Integer nearest-neighbor scaling preserves the small operator strokes.
                import math
                scale = min(4, math.ceil(960 / max(img.size)))
                img = img.convert('RGB').resize((img.width * scale, img.height * scale), Image.Resampling.NEAREST)
                return np.asarray(img)[:, :, ::-1]
            if max(img.size) <= max_side:
                return image_path
            img.thumbnail((max_side, max_side))
            # PaddleOCR 接受 BGR ndarray，和 cv2.imread 的通道顺序保持一致。
            return np.asarray(img.convert('RGB'))[:, :, ::-1]
    except Exception:  # noqa: BLE001  读不了的格式交给引擎报错
        return image_path


def _texts_from(engine, source):
    """把一次推理结果统一成文本行列表（兼容 PaddleOCR 2.x / 3.x）。"""
    lines = []
    if callable(getattr(engine, 'predict', None)):
        for result in engine.predict(source):
            if not isinstance(result, dict):
                result = result.json
            if isinstance(result, str):
                import json
                result = json.loads(result)
            result = result.get('res', result)
            lines.extend(result.get('rec_texts', []))
    else:
        for block in engine.ocr(source, cls=True) or []:
            for item in block or []:
                lines.append(item[1][0])
    return lines


def _candidates_from(engine, source):
    """识别并清洗出所有能求值的算式。"""
    from common.arithmetic import solve

    found = []
    for line in _texts_from(engine, source):
        expr = normalize(line)
        if expr and solve(expr)[0]:
            found.append(expr)
    return found


def _paddle_lines(image_path):
    """Return text lines while keeping the existing fast/accurate retry policy."""
    if not _check_available():
        raise RuntimeError('OCR 引擎未安装。请使用 Python 3.11 或 3.12 的独立环境安装 requirements-ocr.txt 后启动应用。')
    with _lock:
        try:
            source = _prepare(image_path)
            lines = _texts_from(get_ocr(fast=True), source)
            from common.arithmetic import solve
            if not any(normalize(line) and solve(normalize(line))[0] for line in lines):
                # 轻量模型没认出算式时，才用更慢但更准的模型再试一次。
                lines = _texts_from(get_ocr(fast=False), source)
            return lines
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError('OCR 引擎初始化或识别失败，请检查依赖、模型下载和图片格式。') from exc


def _windows_lines(image_path):
    """Read installed Windows OCR locally with a bounded subprocess lifetime."""
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
             str(Path(__file__).with_name('windows_ocr.ps1')),
             '-ImagePath', str(Path(image_path).resolve())],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=True)
        lines = json.loads(result.stdout.lstrip('\ufeff'))['lines']
        if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
            raise ValueError('Invalid Windows OCR response')
        return lines
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError('Windows OCR 无法读取图片，请上传清晰的 PNG/JPG，并确认系统安装了 OCR 语言包；也可安装 requirements-ocr.txt。') from exc


def recognize(image_path):
    """Preserve the single-question endpoint and the Windows fallback."""
    if _check_available():
        try:
            lines = _paddle_lines(image_path)
        except RuntimeError:
            if os.name != 'nt':
                raise
            lines = _windows_lines(image_path)
    elif os.name == 'nt':
        lines = _windows_lines(image_path)
    else:
        raise RuntimeError('OCR 引擎未安装，请安装 requirements-ocr.txt。')
    from common.arithmetic import solve
    candidates = [normalize(line) for line in lines if normalize(line) and solve(normalize(line))[0]]
    if len(candidates) > 1:
        raise RuntimeError('检测到多道算式，请使用整页识别或裁剪为单道题。')
    return candidates[0] if candidates else ''


def _page_candidates(lines):
    """Keep math-like uncertain text for correction instead of silently dropping it."""
    from common.arithmetic import solve
    questions = []
    for line in lines:
        for part in re.split(r'\n|[;；]|\s{2,}', unicodedata.normalize('NFKC', line)):
            part = re.sub(r'^\s*\d+\s*[.、:：]\s+', '', part).strip()
            part = re.sub(r'^\s*\d+\s*、\s*', '', part)
            part = re.sub(r'^\s*\(\d+\)\s*(?=\d)', '', part)
            left = part.split('=')[0].strip()
            # Restrict uncertain candidates to formula-like tokens, not page headings.
            if not left or not re.fullmatch(r'[0-9\s+\-×xX*÷/^().一—－＋mn$?？]+', left):
                continue
            if not re.search(r'\d', left) or (not re.search(r'[+\-×xX*÷/^().$?？]', left) and '=' not in part):
                continue
            if len(left) > 512:
                continue
            # Never silently turn decimal dots into minus signs or insert operators.
            if re.fullmatch(r'[0-9\s+\-×xX*÷/^()一—－＋]+', left):
                expr = normalize(left)
            else:
                expr = left
            questions.append(expr)
            if len(questions) > 200:
                raise RuntimeError('识别到超过 200 道题，请将图片分成几部分上传。')
    return questions


def needs_review(expr):
    from common.arithmetic import solve
    return not re.search(r'[+\-×÷^]', expr) or not solve(expr)[0]


def _windows_page(image_path):
    lines = _windows_lines(image_path)
    for line in lines:
        text = unicodedata.normalize('NFKC', line)
        # Native OCR has no cell positions here: do not fuse adjacent questions.
        if text.count('=') > 1 or ('=' not in text and re.search(r'\d\s+\d', text)):
            raise RuntimeError('Windows OCR 无法分离同一行的多道题，请裁剪为单列或安装 requirements-ocr.txt 后重试。')
    return _page_candidates(lines)


def recognize_page(image_path):
    """Keep whole-page Paddle recognition, falling back to installed Windows OCR."""
    if not _check_available():
        if os.name == 'nt':
            return _windows_page(image_path)
        raise RuntimeError('OCR 引擎未安装，请安装 requirements-ocr.txt 后启动应用。')
    try:
        return _paddle_page(image_path)
    except RuntimeError:
        if os.name != 'nt':
            raise
        return _windows_page(image_path)


def _paddle_page(image_path):
    """Prefer the more complete valid result; preserve uncertain items for review."""
    with _lock:
        try:
            source = _prepare(image_path, max_side=1600)
            questions = _page_candidates(_texts_from(get_ocr(fast=True), source))
            if not questions or any(needs_review(expr) for expr in questions):
                try:
                    alternate = _page_candidates(_texts_from(get_ocr(fast=False), source))
                    rank = lambda items: (sum(not needs_review(expr) for expr in items), len(items))
                    if rank(alternate) > rank(questions):
                        questions = alternate
                except Exception:
                    if not questions:
                        raise
            return questions
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError('OCR 识别失败，请检查依赖、模型或图片格式。') from exc


def warm_up():
    """后台预热：提前加载模型并跑一次推理，避免第一次点击时等初始化。"""
    global _warmed
    if _warmed or not _check_available():
        return
    try:
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont

        image = Image.new('RGB', (360, 140), 'white')
        try:
            font = ImageFont.truetype('arial.ttf', 80)
        except OSError:
            font = ImageFont.load_default()
        ImageDraw.Draw(image).text((20, 30), '1+1', fill='black', font=font)
        array = np.asarray(image)[:, :, ::-1]
        with _lock:
            _texts_from(get_ocr(fast=True), array)
        _warmed = True
    except Exception:  # noqa: BLE001  预热失败不影响正式识别
        pass
