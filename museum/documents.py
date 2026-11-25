"""Render Office documents into numbered PNGs for playback on any terminal."""
import os
from pathlib import Path
import shutil
import subprocess
import threading

FORMATS = {
    '.pdf': 'application/pdf',
    '.ppt': 'application/vnd.ms-powerpoint',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}
DOCUMENT_LIMIT = 50 * 1024**2
PAGE_LIMIT = 100
LOCK = threading.Lock()


def render(source, output):
    if source.suffix.lower() == '.pdf':
        output.mkdir()
        return render_pdf(source, output)
    if os.name != 'nt':
        raise ValueError('Office 文档导入需要在安装 Microsoft Office 的 Windows 服务器上运行')
    output.mkdir()
    script = Path(__file__).with_name('render_document.ps1')
    shell = shutil.which('pwsh.exe') or 'powershell.exe'
    try:
        with LOCK:
            subprocess.run([shell,'-STA','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                            '-File',str(script),'-Source',str(source),'-Output',str(output),
                            '-PageLimit',str(PAGE_LIMIT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
                           timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
        if source.suffix.lower() in {'.doc', '.docx'}:
            pdf = output / 'document.pdf'
            count = render_pdf(pdf, output)
            pdf.unlink(missing_ok=True)
            return count
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


def render_pdf(source, output):
    """PDFium renders one page at a time, without Office or system Poppler."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise ValueError('缺少 PDF 渲染依赖，请运行 python -m pip install -r requirements.txt') from exc
    try:
        with LOCK, pdfium.PdfDocument(str(source)) as doc:
            count = len(doc)
            if not 1 <= count <= PAGE_LIMIT:
                raise ValueError('文档没有可播放页面或超过 100 页')
            for index in range(count):
                page = doc[index]
                bitmap = None
                try:
                    width, height = page.get_size()
                    if min(width, height) <= 0:
                        raise ValueError('PDF 页面尺寸无效')
                    bitmap = page.render(scale=min(2, 1440 / max(width, height)))
                    bitmap.to_pil().save(output / f'{index+1}.png')
                finally:
                    if bitmap is not None:
                        bitmap.close()
                    page.close()
        return count
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('PDF 无法读取，请确认文件未加密且未损坏') from exc
