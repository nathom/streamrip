from setuptools import find_packages, setup

pkg_name = "streamrip"


def read_file(fname):
    with open(fname, "r") as f:
        return f.read()


requirements = read_file("requirements.txt").strip().split()


# https://github.com/pypa/sampleproject/blob/main/setup.py
setup(
    name=pkg_name,
    version="0.1",
    install_requires=requirements,
    py_modules=["streamrip"],
    entry_points={
        "console_scripts": [
            "rip = streamrip.cli:main",
            "streamrip = streamrip.cli:main",
        ],
    },
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "Operating System :: OS Independent",
        "Development Status :: 3 - Alpha",
    ],
    python_requires=">=3.7",
    project_urls={
        "Bug Reports": "https://github.com/nathom/streamrip/issues",
        "Source": "https://github.com/nathom/streamrip",
    },
)

# rm -f dist/*
# python3 setup.py sdist bdist_wheel
# twine upload dist/*
