"""Local verification mail delivery; never log verification links or tokens."""

from email.message import EmailMessage
import smtplib
from urllib.parse import urlsplit


def send_verification_email(recipient, token, base_url, smtp_host='127.0.0.1', smtp_port=1025):
    """Send to local Mailpit using an explicitly configured origin, not Host."""
    origin = urlsplit(base_url)
    if (origin.scheme not in ('http', 'https') or origin.hostname not in ('localhost', '127.0.0.1')
            or origin.username or origin.password or origin.path not in ('', '/')
            or origin.query or origin.fragment):
        raise ValueError('Local BASE_URL must be a localhost HTTP or HTTPS origin.')
    if not isinstance(token, str) or not token or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in token):
        raise ValueError('Invalid verification token.')
    if not isinstance(recipient, str) or '\n' in recipient or '\r' in recipient:
        raise ValueError('Invalid recipient.')
    message = EmailMessage()
    message['From'] = 'Unidays Support <no-reply@example.edu>'
    message['To'] = recipient
    message['Subject'] = 'Verify your Unidays Support account'
    message.set_content('Hello,\n\nOpen this link to continue setting up your account:\n\n'
                        f'{base_url.rstrip("/")}/verify-email#token={token}\n\n'
                        'The link opens a new tab. Choose your final password there and select Verify account. '
                        'The password you entered when starting registration was not saved.\n\n'
                        'This link expires after 30 minutes. If it has expired, request another from the verification page.\n\n'
                        'If you did not request this, you can ignore this message.\n')
    with smtplib.SMTP(smtp_host, smtp_port, timeout=5) as smtp:
        smtp.send_message(message)
