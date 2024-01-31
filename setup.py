from os.path import dirname, exists, realpath
from setuptools import setup, find_packages
import sys
import warnings

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

try:
    # Make sure this fails for old CKAN versions
    import ckan
    ckan_version = [int(v) for v in ckan.__version__.split(".")]
    if ckan_version < [2, 10, 1]:
        raise ValueError(
            f"Your CKAN version {ckan_version} is not supported! If you "
            f"are still on CKAN 2.9.5, then the following package versions "
            f"are supported:"
            f"\n dcor_shared<=0.3.1"
            )
except ImportError:
    warnings.warn("CKAN not installed, supported version check skipped.")

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
    install_requires=[
        "boto3",
        "dclab[s3]>=0.57.3",
    ],
    extras_require={
        # Required for the `dcor_shared.testing` submodule
        "tests": ["requests", "requests_toolbelt", "pytest"]
    },
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
