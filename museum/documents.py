"""Render Office documents into numbered PNGs for playback on any terminal."""
import os
from pathlib import Path
import shutil
import subprocess
import threading

FORMATS = {
    '.ppt': 'application/vnd.ms-powerpoint',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}
DOCUMENT_LIMIT = 50 * 1024**2
PAGE_LIMIT = 100
LOCK = threading.Lock()


def pdf_renderer():
    configured = os.environ.get('MUSEUM_PDFTOPPM')
    if configured:
        return configured if Path(configured).is_file() else None
    installed = shutil.which('pdftoppm')
    if installed:
        return installed
    bundled = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe'
    return str(bundled) if bundled.is_file() else None


def render(source, output):
    if os.name != 'nt':
        raise ValueError('Office 文档导入需要在安装 Microsoft Office 的 Windows 服务器上运行')
    renderer = pdf_renderer() if source.suffix.lower() in {'.doc', '.docx'} else None
    if source.suffix.lower() in {'.doc', '.docx'} and not renderer:
        raise ValueError('Word 文档导入需要 pdftoppm，请安装 Poppler 或设置 MUSEUM_PDFTOPPM')
    output.mkdir()
    script = Path(__file__).with_name('render_document.ps1')
    shell = shutil.which('pwsh.exe') or 'powershell.exe'
    try:
        with LOCK:
            subprocess.run([shell,'-STA','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                            '-File',str(script),'-Source',str(source),'-Output',str(output),
                            '-PageLimit',str(PAGE_LIMIT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
                           timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
        if renderer:
            pdf = output / 'document.pdf'
            subprocess.run([renderer, '-f', '1', '-l', str(PAGE_LIMIT + 1), '-scale-to', '1440',
                            '-png', str(pdf), str(output/'page')], capture_output=True, check=True,
                           timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
            pdf.unlink()
    except subprocess.TimeoutExpired as exc:
        raise ValueError('文档转换超时，请拆分文件并确认 Office 无需交互提示') from exc
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError('文档无法转换，请确认 Office 已安装且文件未加密、未损坏并且不超过 100 页') from exc
    pages = sorted(output.glob('page-*.png'), key=lambda p:int(p.stem.split('-')[1]))
    if not 1 <= len(pages) <= PAGE_LIMIT:
        raise ValueError('文档没有可播放页面或超过 100 页')
    # A stable numeric name is independent of the renderer's zero padding.
    for n, page in enumerate(pages, 1):
        page.rename(output / f'{n}.png')
    return len(pages)
