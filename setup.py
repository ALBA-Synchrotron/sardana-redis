import sys
from setuptools import setup, find_packages


setup(
    name="sardana-redis",
    version="0.2.0",
    description="Sardana BlissData 1.0 Redis Recorder",
    author="Oriol Vallcorba",
    author_email="ovallcorba@cells.es",
    license="GPLv3",
    url="https://github.com/ALBA-Synchrotron/sardana-redis",
    packages=find_packages(),
    install_requires=["sardana"], #"blissdata==1.0rc0"
    python_requires=">=3.5",
)