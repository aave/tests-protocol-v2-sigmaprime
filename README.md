# Brownie Tests

## Installing Brownie

Brownie can be installed via

```sh
pip install eth-brownie
```

Alternatively all required packages can be installed via

```sh
pip install -r requirements.txt
```

## Running the Tests

Tests can be run from the directory `aave-review/tests`

```sh
brownie test
```

Note you can add all the pytest parameters/flags e.g.

* `tests/test_deploy.py`
* `-s`
* `-v`
* `-k <test_name>`


## Initial Setup

This only needs to be done the first time (or possibly just copy `aave-review/tests` next time).

From `aave-review/tests` run

```sh
brownie init
```

Make sure the contracts have been copied to `aave-review/tests/contracts`


## Writing tests

The same as the old `pytest` style. Add a file named `tests_<blah>.py`
to the folder `aave-review/tests/tests`.

Each individual test case in the file created above must be a function named
`test_<test_case>()`.

Checkout the [brownie docs](https://eth-brownie.readthedocs.io/en/stable/tests-pytest-intro.html)
for details on the syntax.

Note `print(dir(Object))` is handy way to see available methods for a python object.
