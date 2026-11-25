from unittest.mock import patch

import pytest

from services.mail import send_verification_email


def test_mail_uses_configured_origin_and_local_smtp():
    with patch('services.mail.smtplib.SMTP') as smtp:
        send_verification_email('student@example.edu', 'token_123', 'http://localhost:5000')
    smtp.assert_called_once_with('127.0.0.1', 1025, timeout=5)
    message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
    assert 'http://localhost:5000/verify-email#token=token_123' in message.get_content()


@pytest.mark.parametrize('origin', ['https://attacker.example', 'http://localhost.attacker.example',
                                    'http://localhost:5000/path', 'http://user@localhost:5000'])
def test_mail_rejects_untrusted_origin(origin):
    with pytest.raises(ValueError):
        send_verification_email('student@example.edu', 'token_123', origin)
