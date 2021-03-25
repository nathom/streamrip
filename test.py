import base64
import json
import logging
import re
import sys
from pprint import pprint

# from music_dl.config import Config
# from music_dl.constants import URL_REGEX
from music_dl.cli import main

# from music_dl.core import MusicDL

# import requests
# from tqdm import tqdm
logger = logging.basicConfig(level=logging.DEBUG)

main()


"""
client = TidalClient()
client.login(**config.creds(client.source))
# https://www.qobuz.com/us-en/label/rhino/download-streaming-albums/7425
# https://www.qobuz.com/us-en/album/chemtrails-over-the-country-club-lana-del-rey/dmm832vafkjdc
album = Album(id='dmm832vafkjdc', client=client)
album.load_meta()
album.download(embed_cover=True)
album.convert('ALAC')
"""

s = """
# converts everything
https://open.qobuz.com/album/
rumours tidal: 68714459
https://open.qobuz.com/album/uhy28719w8ybb
https://open.qobuz.com/playlist/5800943
https://open.qobuz.com/artist/11877118774
https://open.qobuz.com/track/19512574
"""
