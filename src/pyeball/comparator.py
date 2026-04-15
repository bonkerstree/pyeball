import os.path
from .pdf_converter import convert_pdf_to_PIL_images

from dataclasses import dataclass
from .exceptions import *

def compare_documents(doc1_path, doc2_path):
    if os.path.samefile(doc1_path, doc2_path):
        raise PyeballSameDocumentIsBeingCompared
    
    doc1_images = convert_pdf_to_PIL_images(doc1_path)
    doc2_images = convert_pdf_to_PIL_images(doc2_path)
    
    output = ComparisonOutput()
    output.region_diff_count = 0
    for img1, img2 in zip(doc1_images, doc2_images):
        diffs = []
        diff_origin, diff_width, diff_height = _compute_basic_region_diff(img1, img2)
        if diff_origin:
            output.region_diff_count = 1
            diffs.append(OutputDifference(diff_origin, diff_width, diff_height))
            output.diffs = diffs

    return output

def _compute_basic_region_diff(region1, region2):
    """
    Computes the diff of the two regions by converting them to grayscale and then comparing the values
    of the pixels. Returns a tuple containing the coordinates of the first pixel with a diff, the diff width,
    and the diff height.
    """
    grayscale1 = region1.convert('L')
    grayscale2 = region2.convert('L')
    
    diff_origin = None
    diff_height = 0
    max_diff_width = 0
    for y in range(0, grayscale2.height):
        diff_width = 0
        for x in range(0, grayscale1.width):
            pixel_coordinates = (x, y)
            pixel1 = grayscale1.getpixel(pixel_coordinates)
            pixel2 = grayscale2.getpixel(pixel_coordinates)

            if (pixel1 - pixel2) != 0:
                diff_width += 1
                
                if diff_origin is None:
                    diff_origin = pixel_coordinates
                    
        max_diff_width = max(max_diff_width, diff_width)
        if diff_width > 0:
            diff_height += 1
    
    return (diff_origin, max_diff_width, diff_height)

@dataclass
class ComparisonOutput():
    region_diff_count : int = -1
    diffs : list = None

@dataclass
class OutputDifference():
    origin : tuple = (-1, -1)
    width : int = 0
    height : int = 0