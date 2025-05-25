from threading import Lock
from logging import Logger

class TTS160Device:
    """TTS160 Hardware Class
    
    Hardware implementation of TTS160 Alpaca driver.
    This will handle the translation between the hardware and Alpaca driver calls.

    
    """

    def __init__(self, logger: Logger):
        
        #Insert any initialization code here
        