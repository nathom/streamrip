import pytest

from streamrip.client.downloadable import TidalDashDownloadable
from streamrip.client.tidal import TidalClient
from streamrip.exceptions import NonStreamableError

# Same shape as the manifest Tidal returns for a 24-bit/192 kHz track.
MPD = """<?xml version='1.0' encoding='UTF-8'?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT4M36.213S">
  <Period id="0">
    <AdaptationSet id="0" contentType="audio" mimeType="audio/mp4">
      <Representation id="FLAC_HIRES,192000,24" codecs="flac" bandwidth="5611927" audioSamplingRate="192000">
        <SegmentTemplate timescale="192000" initialization="https://cdn.test/0.mp4" media="https://cdn.test/$Number$.mp4" startNumber="1">
          <SegmentTimeline><S d="765952" r="68"/><S d="182261"/></SegmentTimeline>
        </SegmentTemplate>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>"""


def test_parse_mpd():
    info = TidalClient._parse_mpd(MPD)
    assert info == {
        "initialization": "https://cdn.test/0.mp4",
        "media_template": "https://cdn.test/$Number$.mp4",
        "start_number": 1,
        "segments_count": 70,
        "codec": "flac",
    }


def test_dash_segment_urls():
    d = TidalDashDownloadable(None, **TidalClient._parse_mpd(MPD))
    assert d.extension == "flac"
    assert d.segment_urls[0] == "https://cdn.test/0.mp4"
    assert d.segment_urls[1] == "https://cdn.test/1.mp4"
    assert d.segment_urls[-1] == "https://cdn.test/70.mp4"
    assert len(d.segment_urls) == 71


def test_parse_mpd_rejects_unknown_layout():
    with pytest.raises(NonStreamableError):
        TidalClient._parse_mpd(MPD.replace("$Number$", "$Time$"))
    with pytest.raises(NonStreamableError):
        TidalClient._parse_mpd(MPD.replace("SegmentTimeline", "SegmentList"))
