from streamrip.spoofbuz import Spoofer


class TestQobuzSpoofer:
    def test_spoofer_should_get_correct_app_id_and_secrets(self, spoofer: Spoofer):
        app_id = spoofer.get_app_id()
        secrets = spoofer.get_secrets()

        assert app_id == "123456789"
        assert secrets == [
            "10b251c286cfbf64d6b7105f253d9a2e",
            "979549437fcc4a3faad4867b5cd25dcb",
        ]
