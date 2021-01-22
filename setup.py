from os.path import dirname, exists, realpath
from setuptools import setup, find_packages
import sys

author = "Paul Müller"
authors = [author]
description = 'Functionalities shared by the DCOR CKAN extensions'
name = 'dcor_shared'
year = "2020"


sys.path.insert(0, realpath(dirname(__file__))+"/"+name)
try:
    from _version import version  # @UnresolvedImport
except BaseException:
    version = "unknown"


setup(
    name=name,
    author=author,
    author_email='dev@craban.de',
    url='https://github.com/DCOR-dev/dcor_shared',
    version=version,
    packages=find_packages(),
    package_dir={name: name},
    include_package_data=True,
    license="AGPLv3+",
    description=description,
    long_description=open('README.rst').read() if exists('README.rst') else '',
    install_requires=[],
    setup_requires=["pytest-runner"],
    tests_require=["pytest"],
    python_requires='>=3.6, <4',
    keywords=["DCOR"],
    classifiers=[
        'License :: OSI Approved :: GNU Affero General Public License v3 or '
        + 'later (AGPLv3+)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Topic :: Scientific/Engineering :: Visualization',
        'Intended Audience :: Science/Research'
        ],
    platforms=['ALL'],
    )
