#!/usr/bin/env python3
"""Setup de heimdall-timewatch."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="heimdall-timewatch",
    version="1.0.0",
    author="Yoandy Ramirez Delgado",
    description="Detector de timestomping en NTFS ($SI vs $FN + USN Journal)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    url="https://github.com/heindall92/heimdall-timewatch_DFIR",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[],  # Cero dependencias externas (solo stdlib)
    entry_points={
        "console_scripts": [
            "heimdall-timewatch=heimdall_timewatch.cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Security",
        "Intended Audience :: Information Technology",
    ],
)
