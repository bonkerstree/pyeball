import pymupdf
from PIL.Image import Image

def convert_pdf_to_PIL_images(pdf_path) -> list[Image]:
    doc = pymupdf.open(pdf_path)

    page_images = []
    for page in doc:
        pix = page.get_pixmap()
        page_images.append(pix.pil_image())
    
    return page_images