"""Regression checks for currently implemented HTTP hardening controls."""
import secrets
from unittest.mock import patch

import pytest
from bson import ObjectId

from app import create_app
from services.auth import User


def make_app(monkeypatch, production=False):
    monkeypatch.setenv('APP_ENV', 'production' if production else 'development')
    monkeypatch.setenv('SECRET_KEY', secrets.token_hex(32))
    with patch('db.init_app'):
        app = create_app()
    app.config['TESTING'] = True
    return app


def test_production_rejects_missing_or_short_session_secret(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('SECRET_KEY', 'short')
    with patch('db.init_app'), pytest.raises(RuntimeError):
        create_app()
    monkeypatch.delenv('SECRET_KEY')
    with patch('app.dotenv_values', return_value={}), patch('db.init_app'), pytest.raises(RuntimeError):
        create_app()


def test_cookie_headers_and_internal_signin_redirect(monkeypatch):
    app = make_app(monkeypatch, production=True)
    user = User({'_id': ObjectId(), 'role': 'student'})
    client = app.test_client()
    with patch('services.auth.authenticate', return_value=user), patch('services.audit.record'):
        page = client.get('/signin?next=https://attacker.example/')
        with client.session_transaction() as session:
            csrf = session['csrf_token']
        # Use the signed token from the rendered form, not the session's raw value.
        import re
        token = re.search(r'name="csrf_token" value="([^"]+)', page.get_data(as_text=True)).group(1)
        response = client.post('/signin?next=https://attacker.example/', data={
            'identifier': 'fictional@example.edu', 'password': 'fictional password', 'csrf_token': token})
    assert csrf
    assert response.headers['Location'].endswith('/student/home')
    cookie = response.headers['Set-Cookie']
    assert 'HttpOnly' in cookie and 'SameSite=Lax' in cookie and 'Secure' in cookie
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
    assert "script-src 'self'" in response.headers['Content-Security-Policy']
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['Strict-Transport-Security'].startswith('max-age=')
    assert response.headers['Cache-Control'] == 'no-store'


def test_every_registered_post_rejects_missing_csrf(monkeypatch):
    app = make_app(monkeypatch)
    client = app.test_client()
    post_rules = [rule for rule in app.url_map.iter_rules() if 'POST' in rule.methods]
    assert post_rules
    for rule in post_rules:
        # All current dynamic POST routes use an opaque case reference or target ID.
        path = rule.rule.replace('<reference>', 'a' * 32).replace('<target>', 'a' * 24)
        assert '<' not in path, f'Add a harmless example for {rule.endpoint}'
        assert client.post(path).status_code == 400, rule.endpoint


def test_generic_error_pages_but_unhandled_exception_reaches_logs(monkeypatch, caplog):
    app = make_app(monkeypatch)
    app.config.update(TESTING=False, DEBUG=False)

    @app.get('/test-only-error')
    def test_only_error():
        raise RuntimeError('fictional-sensitive-error-marker')

    client = app.test_client()
    assert client.get('/route-that-does-not-exist').status_code == 404
    response = client.get('/test-only-error')
    assert response.status_code == 500
    assert b'fictional-sensitive-error-marker' not in response.data
    # Flask logs unhandled exceptions; production log handling needs redaction.
    assert 'fictional-sensitive-error-marker' in caplog.text
