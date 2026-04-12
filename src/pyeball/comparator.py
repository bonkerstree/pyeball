import os.path
from .pdf_converter import convert_pdf_to_PIL_images

from dataclasses import dataclass
from .exceptions import *

def compare_documents(doc1_path, doc2_path):
    if os.path.samefile(doc1_path, doc2_path):
        raise PyeballSameDocumentIsBeingCompared
    
    doc1_images = convert_pdf_to_PIL_images(doc1_path)
    doc2_images = convert_pdf_to_PIL_images(doc2_path)

    doc1_grayscales = []
    for img in doc1_images:
        doc1_grayscales.append(img.convert('L'))

    doc2_grayscales = []
    for img in doc2_images:
        doc2_grayscales.append(img.convert('L'))
    
    img_diff = 0
    diff_origin = None
    for img1, img2 in zip(doc1_grayscales, doc2_grayscales):
        for x in range(0, img1.width):
            for y in range(0, img2.height):
                pixel_coordinates = (x, y)
                pixel1 = img1.getpixel(pixel_coordinates)
                pixel2 = img2.getpixel(pixel_coordinates)

                if (pixel1 - pixel2) != 0:
                    img_diff += 1
                    if diff_origin is None:
                        diff_origin = pixel_coordinates

    output = ComparisonOutput()
    output.diff_count = 0
    diffs = []
    if img_diff > 0:
        output.diff_count = 1
        diffs.append(OutputDifference(diff_origin))
    output.diffs = diffs
    
    return output

@dataclass
class ComparisonOutput():
    diff_count : int = -1
    diffs : list = None

@dataclass
class OutputDifference():
    origin : tuple = (-1, -1)
    width : int = 0
    height : int = 0