from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="simkl-scrobbler",
    version="1.0.0",
    author="kavinthangavel",
    description="Automatic movie scrobbling for Simkl",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/kavinthangavel/simkl-scrobbler",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
    ],
    python_requires=">=3.7",
    install_requires=[
        "requests>=2.25.0",
        "pygetwindow>=0.0.9",
        "guessit>=3.3.0",
        "python-dotenv>=0.15.0",
        "pywin32>=300",
        "psutil>=5.8.0",
        "colorama>=0.4.4",  # For colorized terminal output
    ],
    entry_points={
        "console_scripts": [
            "simkl-scrobbler=simkl_scrobbler.cli:main",
        ],
    },
)