from setuptools import find_packages, setup

pkg_name = "streamrip"


def read_file(fname):
    with open(fname, "r") as f:
        return f.read()


requirements = read_file("requirements.txt").strip().split()


# https://github.com/pypa/sampleproject/blob/main/setup.py
setup(
    name=pkg_name,
    version="0.4.3",
    author="Nathan",
    author_email="nathanthomas707@gmail.com",
    keywords="lossless, hi-res, qobuz, tidal, deezer, audio, convert, soundcloud, mp3",
    description="A stream downloader for Qobuz, Tidal, SoundCloud, and Deezer.",
    long_description=read_file("README.md"),
    long_description_content_type="text/markdown",
    install_requires=requirements,
    py_modules=["streamrip"],
    entry_points={
        "console_scripts": [
            "rip = streamrip.cli:main",
        ],
    },
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    project_urls={
        "Source": "https://github.com/nathom/streamrip",
        "Bug Reports": "https://github.com/nathom/streamrip/issues",
    },
)

# rm -f dist/*
# python3 setup.py sdist bdist_wheel
# twine upload dist/*
