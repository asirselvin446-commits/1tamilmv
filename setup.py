"""Setup script for 1TamilVT-TG."""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="1tamilvt-tg",
    version="2.0.0",
    author="aj-2-c-2-a",
    description="Telegram Bot for 1TamilMV — Auto-scrape Tamil movie torrents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/aj-2-c-2-a/1tamilvt-tg",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Communications :: Chat",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "1tamilvt-tg=bot.main:main",
        ],
    },
)
