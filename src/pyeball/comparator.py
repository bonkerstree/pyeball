import os.path
from dataclasses import dataclass
from .exceptions import *

def compare_documents(doc1, doc2):
    if os.path.samefile(doc1, doc2):
        raise PyeballSameDocumentIsBeingCompared
    
    output = CompareOutput()
    output.diffs = 0
    
    return output

class CompareOutput():
    diffs : int = -1