import logging
import os

from .exceptions import PyeballMissingDocumentArgs
from .exceptions import PyeballWrongDocumentFormat

logger = logging.getLogger(__name__)

def parse_document_args(args):
    document_paths = None

    try:
        document_paths = (args[1], args[2])        
    except IndexError:
        error_msg = ('Please provide the paths to the documents to be compared with the following format:'
                     '\n\n  python pyeball_main.py document1.pdf document2.pdf\n')
        logger.error(error_msg)
        raise PyeballMissingDocumentArgs(error_msg)
    
    ext = os.path.splitext(args[1])[1].lower()
    if ext != '.pdf':
        error_msg = f'{args[1]} has a \"{ext}\" extension and is not a PDF'
        logger.error(error_msg)
        raise PyeballWrongDocumentFormat(error_msg)
    
    ext = os.path.splitext(args[2])[1].lower()
    if ext != '.pdf':
        error_msg = f'{args[2]} has a \"{ext}\" extension and is not a PDF'
        logger.error(error_msg)
        raise PyeballWrongDocumentFormat(error_msg)

    return document_paths