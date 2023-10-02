dcor_shared
===========

|PyPI Version| |Build Status| |Coverage Status|

Functionalities shared by the DCOR CKAN extensions


Installation
------------
To install the latest release, simply run:

::

    pip install dcor_shared

Testing
-------
Testing is done via vagrant in a virtualmachine using the
`dcor-test <https://app.vagrantup.com/paulmueller/boxes/dcor-test/>` image.
Make sure that `vagrant` and `virtualbox` are installed and run the
following commands in the root of this repository:

::

    # Setup virtual machine using `Vagrantfile`
    vagrant up
    # Run the tests
    vagrant ssh -- sudo bash /testing/vagrant-run-tests.sh


.. |PyPI Version| image:: https://img.shields.io/pypi/v/dcor_shared.svg
   :target: https://pypi.python.org/pypi/dcor_shared
.. |Build Status| image:: https://img.shields.io/github/actions/workflow/status/DCOR-dev/dcor_shared/check.yml
   :target: https://travis-ci.com/DCOR-dev/dcor_shared
.. |Coverage Status| image:: https://img.shields.io/codecov/c/github/DCOR-dev/dcor_shared
   :target: https://codecov.io/gh/DCOR-dev/dcor_shared
