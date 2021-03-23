from setuptools import find_packages, setup

pkg_name = "music-dl"


def read_file(fname):
    with open(fname, "r") as f:
        return f.read()


requirements = read_file("requirements.txt").strip().split()


# https://github.com/pypa/sampleproject/blob/main/setup.py
setup(
    name=pkg_name,
    version="0.9.7",
    url="https://github.com/vitiko98/Qobuz-DL",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "music-dl = music_dl:main",
            "rip = music_dl:main",
        ],
    },
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "Operating System :: OS Independent",
        "Development Status :: 3 - Alpha",
    ],
    package_dir={"", "music-dl"},
    packages=find_packages(where="music-dl"),
    python_requires=">=3.9",
    project_urls={
        "Bug Reports": "https://github.com/nathom/music-dl/issues",
        "Source": "https://github.com/nathom/music-dl",
    },
)

# rm -f dist/*
# python3 setup.py sdist bdist_wheel
# twine upload dist/*
