from __future__ import annotations


def assert_no_side_effect(testcase, provider) -> None:
    testcase.assertEqual(
        list(getattr(provider, "calls", [])),
        [],
        "provider recorded an unexpected side effect",
    )
