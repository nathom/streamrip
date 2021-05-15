import subprocess
import click
import os
import shutil

test_urls = {
    "qobuz": "https://www.qobuz.com/us-en/album/blackest-blue-morcheeba/h4nngz0wgqesc",
    "tidal": "https://tidal.com/browse/album/183284294",
    "deezer": "https://www.deezer.com/us/album/225281222",
    "soundcloud": "https://soundcloud.com/dj-khaled/sets/khaled-khaled",
}


def reset_config():
    global cfg_path
    global new_cfg_path

    p = subprocess.Popen(
        ["rip", "config", "-p"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    out, err = p.communicate()
    cfg_path = out.decode("utf-8").strip()
    # cfg_path = re.search(
    #     r"(/[\w\d\s]+(?:/[\w\d \.]+)*)", out.decode("utf-8")
    # ).group(1)
    new_cfg_path = f"{cfg_path}.tmp"
    shutil.copy(cfg_path, new_cfg_path)
    subprocess.Popen(["rip", "config", "--update"])


def restore_config():
    global cfg_path
    global new_cfg_path

    os.remove(cfg_path)
    shutil.move(new_cfg_path, cfg_path)


def download_albums():
    rip_url = ["rip", "-nd", "-u"]
    procs = []
    for url in test_urls.values():
        procs.append(subprocess.run([*rip_url, url]))

    for p in procs:
        print(p)


def check_album_dl_success(folder, correct):
    if set(os.listdir(folder)) != set(correct):
        click.secho(f"Check for {folder} failed!", fg="red")
    else:
        click.secho(f"Check for {folder} succeeded!", fg="green")


reset_config()
download_albums()
check_album_dl_success(
    "/Users/nathan/StreamripDownloads/Morcheeba - Blackest Blue (2021) [FLAC] [24B-44.1kHz]",
    {
        "04. Morcheeba - Say It's Over.flac",
        "01. Morcheeba - Cut My Heart Out.flac",
        "02. Morcheeba - Killed Our Love.flac",
        "07. Morcheeba - Namaste.flac",
        "03. Morcheeba - Sounds Of Blue.flac",
        "10. Morcheeba - The Edge Of The World.flac",
        "08. Morcheeba - The Moon.flac",
        "09. Morcheeba - Falling Skies.flac",
        "cover.jpg",
        "05. Morcheeba - Sulphur Soul.flac",
        "06. Morcheeba - Oh Oh Yeah.flac",
    },
)

check_album_dl_success(
    "/Users/nathan/StreamripDownloads/KHALED KHALED",
    {
        "05. DJ Khaled - I DID IT (feat. Post Malone, Megan Thee Stallion, Lil Baby & DaBaby).mp3",
        "09. DJ Khaled - THIS IS MY YEAR (feat. A Boogie Wit Da Hoodie, Big Sean, Rick Ross & Puff Daddy).mp3",
        "01. DJ Khaled - THANKFUL (feat. Lil Wayne & Jeremih).mp3",
        "12. DJ Khaled - I CAN HAVE IT ALL (feat. Bryson Tiller, H.E.R. & Meek Mill).mp3",
        "02. DJ Khaled - EVERY CHANCE I GET (feat. Lil Baby & Lil Durk).mp3",
        "08. DJ Khaled - POPSTAR (feat. Drake).mp3",
        "13. DJ Khaled - GREECE (feat. Drake).mp3",
        "04. DJ Khaled - WE GOING CRAZY (feat. H.E.R. & Migos).mp3",
        "10. DJ Khaled - SORRY NOT SORRY (Harmonies by The Hive) [feat. Nas, JAY-Z & James Fauntleroy].mp3",
        "03. DJ Khaled - BIG PAPER (feat. Cardi B).mp3",
        "14. DJ Khaled - WHERE YOU COME FROM (feat. Buju Banton, Capleton & Bounty Killer).mp3",
        "07. DJ Khaled - BODY IN MOTION (feat. Bryson Tiller, Lil Baby & Roddy Ricch).mp3",
        "06. DJ Khaled - LET IT GO (feat. Justin Bieber & 21 Savage).mp3",
        "11. DJ Khaled - JUST BE (feat. Justin Timberlake).mp3",
    },
)

check_album_dl_success(
    "/Users/nathan/StreamripDownloads/Paul Weller - Fat Pop (2021) [FLAC] [24B-44.1kHz]",
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
restore_config()
