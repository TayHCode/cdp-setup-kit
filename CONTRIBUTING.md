# Contributing

Run the suite from the checkout. The top-level option loads the test guard.
Run only one suite process at a time.

```sh
python3 -m unittest discover -s tests -t . -q
python3.11 -m unittest discover -s tests -t . -q
```

Runtime and tests use the Python standard library only. All package side
effects belong in `system.py`; other modules accept a `System`. Tests use
`FakeSystem` with isolated storage and `FakeCdpServer` with port 0.
`CDP_SETUP_KIT_FORBID_REAL=1` blocks process launches, scheduler commands,
and writes outside `CDP_SETUP_KIT_DIR`. Keep it on during development.

Never test against a signed-in profile, an existing debugging port, or a
real sign-in entry. Use placeholders only in code, fixtures and docs.
No personal information, binary files, credentials or hosted CI belongs here.
Do not add a dependency, browser feature, background service or timer.

The private-terms check skips unless `CDP_SETUP_KIT_DENYLIST` names an external
term file. It checks files, paths and all commit identities and messages,
and reports counts and locations without showing terms. It accepts a JSON
array, a `terms` object, categories of term lists, or one term per line.

Only an owner or contributor on a disposable desktop may opt into
`CDP_SETUP_KIT_REAL_CHROME=1 python -m unittest tests.test_real_chrome -v`.
That test creates a fresh temporary profile, allocates its own port, starts
Chrome twice, checks the endpoint and exposure, and ends only its own child
process. It never uses existing config or profiles. Do not enable it in the
normal suite. Read [verification](docs/verification.md) first.

Python 3.9 is the declared floor; syntax is checked with that grammar.
The build's executed interpreters are recorded separately. A syntax check
does not establish runtime compatibility with an untested interpreter.
