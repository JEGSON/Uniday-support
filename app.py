"""Local UI review app. Authentication and account storage are not implemented."""
import os
import secrets

from flask import Flask, render_template, request
from flask_wtf.csrf import CSRFProtect, CSRFError


def create_app():
    app = Flask(__name__)
    # Ephemeral key is for local review only. Production must load a persistent,
    # securely managed key and use appropriately configured secure cookies/TLS.
    app.config.update(SECRET_KEY=secrets.token_hex(32), MAX_CONTENT_LENGTH=16384,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
    CSRFProtect(app)

    @app.after_request
    def security_headers(response):
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if request.endpoint in ('signin', 'signup'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(CSRFError)
    def expired_form(_error):
        return render_template('form_expired.html'), 400

    @app.get('/')
    def landing():
        return render_template('landing.html')

    @app.route('/signin', methods=['GET', 'POST'])
    def signin():
        if request.method == 'POST':
            # Integrate authentication here. Until then, never claim success or
            # disclose whether an account exists; do not log or retain secrets.
            return render_template('signin.html', identifier=request.form.get('identifier', '')[:254],
                                   error='Sign-in is currently unavailable. Please try again later.'), 503
        return render_template('signin.html')

    @app.route('/signup', methods=['GET', 'POST'])
    def signup():
        if request.method == 'GET':
            return render_template('signup.html')
        values = {key: request.form.get(key, '').strip() for key in ('full_name', 'student_id', 'email', 'course')}
        errors = {}
        for key, label, maximum in (('full_name', 'your name', 120), ('student_id', 'your student ID', 64),
                                    ('course', 'your course', 160)):
            if not values[key] or len(values[key]) > maximum:
                errors[key] = f'Enter {label} using no more than {maximum} characters.'
        email = values['email']
        if not email or len(email) > 254 or email.count('@') != 1 or any(c.isspace() for c in email) or not all(email.split('@')):
            errors['email'] = 'Enter your university email address.'
        password = request.form.get('password', '')
        confirmation = request.form.get('confirm_password', '')
        if not 15 <= len(password) <= 128 or not password.strip():
            errors['password'] = 'Use a password between 15 and 128 characters.'
        if password != confirmation or not confirmation:
            errors['confirm_password'] = 'Those passwords do not match yet.'
        if errors:
            return render_template('signup.html', errors=errors, values=values), 400
        # Account creation requires a real identity verification and persistence
        # service. This local UI review does not create accounts or store passwords.
        return render_template('signup.html', values=values, errors={'service': 'Account creation is currently unavailable. Please try again later.'}), 503

    return app
