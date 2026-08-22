"""
Reading a one-time code out of an email (FR-A5).

Entering the wrong six digits into a real login form is worse than entering
none, so the extractor is conservative: a message must read as a verification
mail before any number in it is trusted. These pin the shapes providers use and,
just as important, the numbers that must NOT be read as codes.
"""

from __future__ import annotations

from agent import inbox


def test_code_right_after_the_word():
    assert inbox.extract_code("Verify your account", "Your code is 123456. Expires soon.") == "123456"
    assert inbox.extract_code("Security code", "OTP: 4821") == "4821"


def test_six_digit_in_subject():
    assert inbox.extract_code("847213 is your verification code", "") == "847213"


def test_spaced_and_dashed_codes_are_joined():
    assert inbox.extract_code("Your login code", "Enter code 12 34 56 to continue") == "123456"
    assert inbox.extract_code("One-time passcode", "code: 482-193") == "482193"


def test_a_number_without_verification_context_is_ignored():
    # An order confirmation with a six-digit order number is not an OTP.
    assert inbox.extract_code("Order 483920 shipped", "Your package is on its way.") is None


def test_no_number_at_all():
    assert inbox.extract_code("Verify your email", "Click the link to confirm.") is None
