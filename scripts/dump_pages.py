from pathlib import Path
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent import pdf_tools

PDF = Path("data/patients/patient.pdf")
OUT = Path("outputs/patient/images")
OUT.mkdir(parents=True, exist_ok=True)

print("Rendering images...")
images = pdf_tools._render_pdf_images(PDF)
if not images:
    print("No images rendered")
else:
    for i, img in enumerate(images[:5], start=1):
        outp = OUT / f"page_{i}.png"
        try:
            img.save(outp)
            print("Saved", outp)
        except Exception as e:
            print("Failed to save page", i, e)
print("Done")
