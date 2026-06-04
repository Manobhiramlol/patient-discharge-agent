"""PDF ingestion with retry, adaptive document extraction, OCR fallback, and failure reporting."""

from __future__ import annotations

import shutil
import signal
import time

from pathlib import Path
from typing import Any

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None

try:
    from pdf2image import convert_from_path
except ImportError:  # pragma: no cover
    convert_from_path = None

try:
    import pytesseract
    # Set explicit Tesseract path for Windows to avoid PATH issues
    if shutil.which("tesseract") is None:
        # Try common Windows installation paths
        possible_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        for path in possible_paths:
            if Path(path).exists():
                pytesseract.pytesseract.tesseract_cmd = path
                break
except ImportError:  # pragma: no cover
    pytesseract = None

# EasyOCR disabled for performance - using pytesseract only
# try:
#     import easyocr
# except ImportError:  # pragma: no cover
#     easyocr = None

try:
    from PIL import Image, ImageOps, ImageFilter
except ImportError:  # pragma: no cover
    Image = None
    ImageOps = None
    ImageFilter = None

from pypdf import PdfReader

MAX_RETRIES = 2
MIN_TEXT_THRESHOLD = 400
MIN_NATIVE_TEXT_THRESHOLD = 100
MIN_OCR_CONFIDENCE = 0.50
OCR_PAGE_LIMIT = 20
OCR_DPI = 150
MAX_OCR_SECONDS_PER_PAGE = 8


class TimeoutException(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutException("OCR operation timed out")


def list_patient_pdfs(patient_dir: Path) -> list[Path]:
    if not patient_dir.is_dir():
        return []
    return sorted(patient_dir.glob("*.pdf"))


def read_pdf_text(path: Path, max_retries: int = MAX_RETRIES, backoff_sec: float = 0.5) -> dict[str, Any]:
    """Extract text from a PDF. Returns a result object and never raises."""
    last_err: str | None = None

    for attempt in range(1, max_retries + 1):
        try:
            if not path.exists():
                return {
                    "ok": False,
                    "path": str(path),
                    "error": "file_not_found",
                    "flag": "PDF_EXTRACTION_FAILED",
                    "attempts": attempt,
                }

            pages, image_count = _extract_native_text(path)
            tables = _extract_tables(path)
            full_text = "\n\n".join(pages).strip()
            quality = _document_quality_summary(full_text, pages, image_count, tables)

            if _should_fallback_to_ocr(full_text, pages, image_count, tables):
                ocr_result = _ocr_pdf(path)
                if ocr_result.get("ok") and ocr_result.get("pages"):
                    ocr_pages = ocr_result["pages"]
                    combined_pages = _combine_native_and_ocr_pages(pages, ocr_pages)
                    full_text = "\n\n".join(combined_pages).strip()
                    confidence = ocr_result.get("confidence")
                    page_metadata = ocr_result.get("page_metadata", [])
                    quality = _document_quality_summary(full_text, combined_pages, image_count, tables, page_metadata)
                    return {
                        "ok": True,
                        "path": str(path),
                        "filename": path.name,
                        "page_count": len(combined_pages),
                        "text": full_text,
                        "pages": combined_pages,
                        "char_count": len(full_text),
                        "tables": tables,
                        "document_quality": quality,
                        "attempts": attempt,
                        "extraction_method": "ocr_fallback",
                    }

                if full_text or tables:
                    quality.update({"ocr_used": True, "confidence": ocr_result.get("confidence"), "method": "ocr_attempted"})
                    return {
                        "ok": True,
                        "path": str(path),
                        "filename": path.name,
                        "page_count": len(pages),
                        "text": full_text,
                        "pages": pages,
                        "char_count": len(full_text),
                        "tables": tables,
                        "document_quality": quality,
                        "attempts": attempt,
                        "extraction_method": "native+ocr_failed",
                    }

                return {
                    "ok": False,
                    "path": str(path),
                    "filename": path.name,
                    "error": "unreadable",
                    "flag": "PDF_EXTRACTION_FAILED",
                    "attempts": attempt,
                    "detail": ocr_result.get("detail") or last_err or "empty text — PDF treated as unreadable",
                    "page_count": len(pages),
                    "pages": pages,
                    "tables": tables,
                    "document_quality": quality,
                }

            return {
                "ok": True,
                "path": str(path),
                "filename": path.name,
                "page_count": len(pages),
                "text": full_text,
                "pages": pages,
                "char_count": len(full_text),
                "tables": tables,
                "document_quality": quality,
                "attempts": attempt,
                "extraction_method": "native",
            }

        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            if attempt < max_retries:
                time.sleep(backoff_sec * attempt)

    return {
        "ok": False,
        "path": str(path),
        "filename": path.name if path.exists() else None,
        "error": "read_failed",
        "flag": "PDF_EXTRACTION_FAILED",
        "attempts": max_retries,
        "detail": last_err,
    }


def _document_quality_summary(full_text: str, pages: list[str], image_count: int, tables: list[dict[str, Any]], ocr_metadata: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    text_pages = sum(1 for page in pages if page and page.strip())
    total_pages = max(len(pages), 1)
    summary = {
        "ocr_used": False,
        "confidence": None,
        "method": "native",
        "images_present": image_count > 0,
        "image_count": image_count,
        "tables_found": len(tables),
        "native_text_pages": text_pages,
        "native_page_count": len(pages),
        "native_text_length": len(full_text),
        "native_text_ratio": text_pages / total_pages,
        "low_confidence": False,
    }
    if ocr_metadata:
        summary["ocr_used"] = True
        summary["ocr_page_metadata"] = ocr_metadata
        summary["ocr_pages_processed"] = len(ocr_metadata)
        avg_conf = sum(m.get("ocr_confidence", 0) for m in ocr_metadata) / len(ocr_metadata) if ocr_metadata else 0
        summary["confidence"] = avg_conf
        summary["low_confidence"] = avg_conf < MIN_OCR_CONFIDENCE
    return summary


def _extract_native_text(path: Path) -> tuple[list[str], int]:
    pages: list[str] = []
    image_count = 0

    print(f"[PDF] Extracting native text from {path.name}")
    
    if fitz is not None:
        try:
            with fitz.open(str(path)) as doc:
                for page in doc:
                    pages.append(page.get_text("text") or "")
                    image_count += len(page.get_images(full=True))
            print(f"[PDF] Native extraction complete with fitz: {len(pages)} pages, {image_count} images")
            return pages, image_count
        except Exception:
            pages = []
            image_count = 0

    if pdfplumber is not None:
        try:
            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages:
                    pages.append(page.extract_text() or "")
                    image_count += len(page.images or [])
            print(f"[PDF] Native extraction complete with pdfplumber: {len(pages)} pages, {image_count} images")
            return pages, image_count
        except Exception:
            pages = []
            image_count = 0

    reader = PdfReader(str(path))
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    print(f"[PDF] Native extraction complete with pypdf: {len(pages)} pages")
    return pages, image_count


def _extract_tables(path: Path) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    if pdfplumber is None:
        return tables

    print(f"[TABLE] Extracting tables from {path.name}")
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                for table in page.extract_tables():
                    if not table:
                        continue
                    rows: list[str] = []
                    for row in table:
                        safe_row = [str(cell or "") for cell in row]
                        rows.append(" | ".join(safe_row))
                    tables.append({"page": page_index, "table": "\n".join(rows)})
    except Exception:
        return tables
    print(f"[TABLE] Extracted {len(tables)} tables")
    return tables


def _should_fallback_to_ocr(full_text: str, pages: list[str], image_count: int, tables: list[dict[str, Any]]) -> bool:
    total_pages = len(pages)
    text_pages = sum(1 for page in pages if page and page.strip())
    text_ratio = text_pages / max(total_pages, 1)

    # Smart OCR trigger: only OCR if native text is insufficient
    if total_pages == 0:
        return True
    if len(full_text) < MIN_NATIVE_TEXT_THRESHOLD:
        return True
    if image_count > 0 and text_ratio < 0.5:
        return True
    if tables and len(full_text) < MIN_TEXT_THRESHOLD * 2:
        return True
    return False


def _combine_native_and_ocr_pages(native_pages: list[str], ocr_pages: list[str]) -> list[str]:
    max_pages = max(len(native_pages), len(ocr_pages))
    combined: list[str] = []
    for idx in range(max_pages):
        native_text = native_pages[idx].strip() if idx < len(native_pages) else ""
        ocr_text = ocr_pages[idx].strip() if idx < len(ocr_pages) else ""
        if native_text and ocr_text:
            combined.append(f"{native_text}\n\n{ocr_text}")
        else:
            combined.append(native_text or ocr_text)
    return combined


def _render_pdf_images(path: Path) -> list[Any]:
    images: list[Any] = []

    if convert_from_path is not None:
        try:
            # limit pages and dpi to keep OCR runs responsive
            try:
                images = convert_from_path(str(path), dpi=OCR_DPI, first_page=1, last_page=OCR_PAGE_LIMIT)
            except TypeError:
                # older pdf2image versions may not support first_page/last_page kwargs
                images = convert_from_path(str(path), dpi=OCR_DPI)
            if images:
                return images
        except Exception:
            images = []

    if fitz is not None and Image is not None:
        try:
            with fitz.open(str(path)) as doc:
                for i, page in enumerate(doc, start=1):
                    if i > OCR_PAGE_LIMIT:
                        break
                    pix = page.get_pixmap(matrix=fitz.Matrix(OCR_DPI / 72, OCR_DPI / 72), alpha=False)
                    mode = "RGB" if pix.n < 4 else "RGBA"
                    image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                    images.append(image)
            if images:
                return images
        except Exception:
            images = []

    if pdfplumber is not None and Image is not None:
        try:
            with pdfplumber.open(str(path)) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    if i > OCR_PAGE_LIMIT:
                        break
                    page_image = page.to_image(resolution=OCR_DPI)
                    pil_image = page_image.original
                    if pil_image is not None:
                        images.append(pil_image)
            if images:
                return images
        except Exception:
            images = []

    return images


def _ocr_pdf(path: Path) -> dict[str, Any]:
    pages: list[str] = []
    confidences: list[float] = []
    backend = None
    render_error = None
    page_metadata: list[dict[str, Any]] = []

    # print(f"[OCR] Starting OCR for {path.name}")  # Reduced for demo logs
    images = _render_pdf_images(path)
    if not images:
        print(f"[OCR] No images rendered for {path.name}")
        return {
            "ok": False,
            "detail": "OCR fallback unavailable: no image rendering backend available",
        }

    if pytesseract is not None:
        # Check if tesseract is available via PATH or explicit path
        tesseract_available = shutil.which("tesseract") is not None
        if not tesseract_available:
            # Check if explicit path was set at import time
            tesseract_available = hasattr(pytesseract.pytesseract, 'tesseract_cmd') and Path(pytesseract.pytesseract.tesseract_cmd).exists()
        
        if tesseract_available:
            backend = "tesseract"
        else:
            print(f"[OCR] Tesseract not available")
            return {
                "ok": False,
                "detail": "OCR fallback unavailable: tesseract not available",
            }
    else:
        print(f"[OCR] pytesseract not installed")
        return {
            "ok": False,
            "detail": "OCR fallback unavailable: pytesseract not installed",
        }

    for idx, image in enumerate(images, start=1):
        # print(f"[OCR] Processing page {idx}/{len(images)}")  # Reduced for demo logs
        try:
            page_image = image
            if Image is not None and ImageOps is not None and isinstance(page_image, Image.Image):
                page_image = page_image.convert("L")
                page_image = ImageOps.autocontrast(page_image)
                # upscale small images to help OCR and apply a sharpen filter
                try:
                    w, h = page_image.size
                    target_w = 1400
                    if w < target_w:
                        scale = target_w / max(w, 1)
                        new_size = (int(w * scale), int(h * scale))
                        page_image = page_image.resize(new_size, Image.LANCZOS)
                except Exception:
                    pass
                if ImageFilter is not None:
                    try:
                        page_image = page_image.filter(ImageFilter.SHARPEN)
                    except Exception:
                        pass

            if backend == "tesseract":
                try:
                    # Set timeout signal for this page
                    if hasattr(signal, 'SIGALRM'):
                        signal.signal(signal.SIGALRM, timeout_handler)
                        signal.alarm(MAX_OCR_SECONDS_PER_PAGE)
                    
                    data = pytesseract.image_to_data(page_image, lang="eng", output_type=pytesseract.Output.DICT)
                    page_text = " ".join([t for t in data.get("text", []) if t and t.strip()])
                    page_conf = [float(conf) for conf in data.get("conf", []) if str(conf).strip() and conf not in ("-1", "")]
                    confidences.extend(page_conf)
                    
                    if hasattr(signal, 'SIGALRM'):
                        signal.alarm(0)  # Cancel alarm
                    
                    page_avg_conf = sum(page_conf) / len(page_conf) if page_conf else 0
                    page_metadata.append({
                        "page": idx,
                        "ocr_used": True,
                        "ocr_confidence": page_avg_conf / 100.0,
                        "text_length": len(page_text),
                    })
                except TimeoutException:
                    print(f"[OCR] Page {idx} timed out after {MAX_OCR_SECONDS_PER_PAGE}s")
                    if hasattr(signal, 'SIGALRM'):
                        signal.alarm(0)
                    page_text = ""
                    page_metadata.append({
                        "page": idx,
                        "ocr_used": True,
                        "ocr_confidence": 0.0,
                        "text_length": 0,
                        "timeout": True,
                    })
                except Exception:
                    page_text = pytesseract.image_to_string(page_image, lang="eng") or ""
            pages.append(page_text)
        except Exception as exc:
            render_error = str(exc)
            pages.append("")
            page_metadata.append({
                "page": idx,
                "ocr_used": False,
                "error": str(exc),
            })

    if not any(text.strip() for text in pages):
        return {
            "ok": False,
            "detail": "OCR produced no readable text" + (f": {render_error}" if render_error else ""),
            "pages": pages,
            "backend": backend,
        }

    confidence = None
    if confidences:
        confidence = min(max(sum(confidences) / len(confidences), 0.0), 100.0) / 100.0

    print(f"[OCR] Completed {len(pages)} pages, confidence: {confidence:.2f}")
    
    # Graceful degradation: if confidence is too low, mark for review
    if confidence is not None and confidence < MIN_OCR_CONFIDENCE:
        print(f"[OCR] Low confidence - marking for manual review")
        return {
            "ok": True,
            "pages": pages,
            "confidence": confidence,
            "backend": backend,
            "page_metadata": page_metadata,
            "status": "PARTIAL_EXTRACTION",
            "requires_review": True,
        }
    
    return {
        "ok": True,
        "pages": pages,
        "confidence": confidence,
        "backend": backend,
        "page_metadata": page_metadata,
    }
