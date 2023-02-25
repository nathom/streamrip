import os
import shutil
import subprocess

from click import echo, secho

test_urls = {
    # "qobuz": "https://www.qobuz.com/us-en/album/blackest-blue-morcheeba/h4nngz0wgqesc",
    # "tidal": "https://tidal.com/browse/album/183284294",
    "deezer": "https://www.deezer.com/us/album/228599362",
    # "soundcloud": "https://soundcloud.com/dj-khaled/sets/khaled-khaled",
}



def download_albums():
    rip_url = ["poetry", "run", "rip", "url", "-n", "-d", "/tmp/"]
    procs = []
    for url in test_urls.values():
        procs.append(subprocess.run([*rip_url, url]))

    for p in procs:
        echo(p)


def check_album_dl_success(folder, correct):
    if set(os.listdir(folder)) != set(correct):
        secho(f"Check for {folder} failed!", fg="red")
    else:
        secho(f"Check for {folder} succeeded!", fg="green")


def test_all():
    download_albums()

    check_album_dl_success(
        "/tmp/Paul Weller - Fat Pop (2021) [FLAC] [16B-44.1kHz]",
        {
            "01. Paul Weller - Cosmic Fringes.flac",
            "11. Paul Weller - In Better Times.flac",
            "05. Paul Weller - Glad Times.flac",
            "08. Paul Weller - That Pleasure.flac",
            "04. Paul Weller - Shades Of Blue.flac",
            "12. Paul Weller - Still Glides The Stream.flac",
            "03. Paul Weller - Fat Pop.flac",
            "cover.jpg",
            "02. Paul Weller - True.flac",
            "09. Paul Weller - Failed.flac",
            "06. Paul Weller - Cobweb  Connections.flac",
            "10. Paul Weller - Moving Canvas.flac",
            "07. Paul Weller - Testify.flac",
        },
    )

if __name__ == "__main__":
    test_all()
