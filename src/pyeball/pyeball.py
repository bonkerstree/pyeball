import logging
import sys
import os.path

from .exceptions import PyeballMissingDocumentArgs
from .exceptions import PyeballWrongDocumentFormat

logger_name = 'pyeball'
logger = logging.getLogger(logger_name)
logging.basicConfig(filename=f'{logger_name}.log',
                        format='%(asctime)s.%(msecs)03d %(module)s.py: %(funcName)s(): [%(levelname)s] %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=logging.INFO)

def _parse_document_args(args):
    document_paths = None

    try:
        document_paths = (args[1], args[2])        
    except IndexError:
        logger.error('Please provide the paths to the documents to be compared with the following format:'
                     '\n\n  python pyeball.py document1.pdf document2.pdf\n')
        raise PyeballMissingDocumentArgs
    
    ext = os.path.splitext(args[1])[1].lower()
    if ext != '.pdf':
        logger.error(f'{args[1]} has a \"{ext}\" extension and is not a PDF')
        raise PyeballWrongDocumentFormat
    
    ext = os.path.splitext(args[2])[1].lower()
    if ext != '.pdf':
        logger.error(f'{args[2]} has a \"{ext}\" extension and is not a PDF')
        raise PyeballWrongDocumentFormat

    return document_paths

def main():
    logger.info('==================== Starting up pyeball ====================')
    doc1, doc2 = _parse_document_args(sys.argv)
    logger.info('==================== Closing down pyeball ====================')

if __name__ == "__main__":
    main()