import pytest

from app.redaction import RedactionResult, redact


def test_email_redacted():
    result = redact("Contact admin@example.com for help")
    assert "admin@example.com" not in result.text
    assert "<EMAIL_ADDRESS>" in result.text
    assert result.is_redacted is True


def test_phone_redacted():
    result = redact("Call us at 555-867-5309")
    assert "555-867-5309" not in result.text
    assert result.is_redacted is True


def test_credit_card_redacted():
    result = redact("Pay with 4111 1111 1111 1111")
    assert "4111 1111 1111 1111" not in result.text
    assert result.is_redacted is True


def test_ip_address_redacted():
    result = redact("Server IP is 192.168.1.100")
    assert "192.168.1.100" not in result.text
    assert result.is_redacted is True


def test_api_key_sk_prefix_redacted():
    result = redact("Use sk-test-1234567890abcdef to authenticate")
    assert "sk-test-1234567890abcdef" not in result.text
    assert result.is_redacted is True


def test_password_assignment_redacted():
    result = redact("Config has password=secret123 set")
    assert "secret123" not in result.text
    assert result.is_redacted is True


def test_password_colon_syntax_redacted():
    result = redact("Use password: hunter2 to log in")
    assert "hunter2" not in result.text
    assert result.is_redacted is True


def test_clean_text_not_redacted():
    result = redact("What are your business hours on weekends?")
    assert result.text == "What are your business hours on weekends?"
    assert result.is_redacted is False


def test_multiple_entities_in_one_string():
    result = redact("Email foo@bar.com and key sk-test-1234567890abcdef both present")
    assert "foo@bar.com" not in result.text
    assert "sk-test-1234567890abcdef" not in result.text
    assert result.is_redacted is True


def test_returns_redaction_result_type():
    result = redact("hello world")
    assert isinstance(result, RedactionResult)
    assert isinstance(result.text, str)
    assert isinstance(result.is_redacted, bool)
