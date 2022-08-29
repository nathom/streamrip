import pytest
import requests
from pytest_mock import MockerFixture

from streamrip.spoofbuz import Spoofer


@pytest.fixture
def spoofer(mocker: MockerFixture) -> Spoofer:
    mocked_bundle = mocker.mock_module.MagicMock()
    mocked_bundle.text = '<script src="/resources/6.1.1-b039/bundle.js"></script>'

    mocked_bundle_req = mocker.mock_module.MagicMock()
    mocked_bundle_req.text = r'bar?n.qobuzapi={app_id:"123456789",app_secret:"04e4f0e4fdf1e4f585dfc64c790a7a53",base_port:"80",base_url:"https://www.qobuz.com",base_method:"/api.json/0.2/"},n.base_url="https://nightly-play.qobuz.com"?foo?d.initialSeed("MTBiMjUxYzI4NmNmYmY2NGQ2YjcxMD",window.utimezone.london)?foo?d.initialSeed("MmFiNzEzMWQzODM2MjNjZjQwM2NmM2",window.utimezone.algier)?bar?d.initialSeed("OTc5NTQ5NDM3ZmNjNGEzZmFhZDQ4Nj",window.utimezone.berlin)?bar?n={dublin:35,london:37,algier:39,paris:44,berlin:53,timezones:[{offset:"GMT",name:"Africa/Abidjan"},{offset:"GMT",name:"Europe/Dublin",info:"FkYzliYjFjMDM=MWNlNTlmYjA5ZDQ2",extras:"NGM4NGJlNmE4YzU4YTQyMDA0OTU="},{offset:"GMT",name:"Europe/Lisbon"},{offset:"GMT",name:"Europe/London",info:"VmMjUzZDlhMmU=MWNlNTlmYjA5ZDQ2",extras:"NGM4NGJlNmE4YzU4YTQyMDA0OTU="},{offset:"UTC",name:"UTC"},{offset:"GMT+01:00",name:"Africa/Algiers",info:"Q0Njc2YzU2YjY=MWNlNTlmYjA5ZDQ2",extras:"NGM4NGJlNmE4YzU4YTQyMDA0OTU="},{offset:"GMT+01:00",name:"Africa/Windhoek"},{offset:"GMT+01:00",name:"Atlantic/Azores"},{offset:"GMT+01:00",name:"Atlantic/Stanley"},{offset:"GMT+01:00",name:"Europe/Amsterdam"},{offset:"GMT+01:00",name:"Europe/Paris",info:"A0MDI2NTgyZmU=MWNlNTlmYjA5ZDQ2",extras:"NGM4NGJlNmE4YzU4YTQyMDA0OTU="},{offset:"GMT+01:00",name:"Europe/Belgrade"},{offset:"GMT+01:00",name:"Europe/Brussels"},{offset:"GMT+02:00",name:"Africa/Cairo"},{offset:"GMT+02:00",name:"Africa/Blantyre"},{offset:"GMT+02:00",name:"Asia/Beirut"},{offset:"GMT+02:00",name:"Asia/Damascus"},{offset:"GMT+02:00",name:"Asia/Gaza"},{offset:"GMT+02:00",name:"Asia/Jerusalem"},{offset:"GMT+02:00",name:"Europe/Berlin",info:"diNWNkMjVkY2I=MWNlNTlmYjA5ZDQ2",extras:"NGM4NGJlNmE4YzU4YTQyMDA0OTU="},{offset:"GMT+03:00",name:"Africa/Addis_Ababa"}]}'
    mocked_get = mocker.patch.object(requests, "get")
    mocked_get.side_effect = [mocked_bundle, mocked_bundle_req]

    spoofer = Spoofer()
    return spoofer
