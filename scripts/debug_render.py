import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

print('ROOT', ROOT)

from agent import pdf_tools

path = Path('data/patients/patient.pdf')
print('path exists', path.exists(), path.resolve())
print('fitz', pdf_tools.fitz)
print('pdfplumber', pdf_tools.pdfplumber)
print('convert_from_path', pdf_tools.convert_from_path)
print('Image', pdf_tools.Image)
print('ImageOps', pdf_tools.ImageOps)
print('ImageFilter', pdf_tools.ImageFilter)
print('easyocr', pdf_tools.easyocr)
print('pytesseract', pdf_tools.pytesseract)
import shutil
print('tesseract_bin', shutil.which('tesseract'))

try:
    print('\nTesting fitz...')
    import fitz
    with fitz.open(str(path)) as doc:
        print('fitz pages', len(doc))
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(150/72,150/72), alpha=False)
        print('pix', pix.width, pix.height, pix.n)
        img = pdf_tools.Image.frombytes('RGB' if pix.n < 4 else 'RGBA', [pix.width, pix.height], pix.samples)
        print('fitz image', img.size, img.mode)
except Exception as e:
    import traceback
    print('fitz error', e)
    print(traceback.format_exc())

try:
    print('\nTesting pdfplumber...')
    import pdfplumber
    with pdfplumber.open(str(path)) as pdf:
        print('pdfplumber pages', len(pdf.pages))
        page = pdf.pages[0]
        print('page images count', len(page.images or []))
        image = page.to_image(resolution=150).original
        print('pdfplumber image', image.size, image.mode)
except Exception as e:
    import traceback
    print('pdfplumber error', e)
    print(traceback.format_exc())

try:
    print('\nTesting pdf2image...')
    from pdf2image import convert_from_path
    imgs = convert_from_path(str(path), dpi=150, first_page=1, last_page=1)
    print('pdf2image count', len(imgs))
    print('pdf2image image', imgs[0].size, imgs[0].mode)
except Exception as e:
    import traceback
    print('pdf2image error', e)
    print(traceback.format_exc())

try:
    print('\nTesting _render_pdf_images...')
    imgs = pdf_tools._render_pdf_images(path)
    print('render count', len(imgs))
    for i, img in enumerate(imgs[:3], start=1):
        print('img', i, type(img), getattr(img, 'size', None), getattr(img, 'mode', None))
except Exception as e:
    import traceback
    print('_render_pdf_images error', e)
    print(traceback.format_exc())
