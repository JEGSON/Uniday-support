"""Flask application factory and student support pages."""
import secrets
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, render_template, request, redirect, session, url_for
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from dotenv import dotenv_values
from pymongo.errors import DuplicateKeyError, PyMongoError
from email_validator import EmailNotValidError, validate_email

import db
from services.users import validate_signup
from services import audit, auth, enrollment, tokens, cases as case_service, stats, audit_viewer, admin_users as user_admin
from services.passwords import validate_password, hash_password
from services.decorators import role_required
import mock_data


def create_app():
    app = Flask(__name__)
    settings = dotenv_values(Path(app.root_path) / '.env', interpolate=False)
    key = os.environ.get('SECRET_KEY') or settings.get('SECRET_KEY')
    production = os.environ.get('APP_ENV', 'development') == 'production'
    if production and (not key or len(key) < 32):
        raise RuntimeError('A strong SECRET_KEY is required in production.')
    # Ephemeral key is for local review only. Production must load a persistent,
    # securely managed key and use appropriately configured secure cookies/TLS.
    app.config.update(SECRET_KEY=key or secrets.token_hex(32), MAX_CONTENT_LENGTH=16384,
                      BASE_URL=os.environ.get('BASE_URL') or settings.get('BASE_URL') or 'http://127.0.0.1:5000',
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=production, PERMANENT_SESSION_LIFETIME=timedelta(hours=1))
    CSRFProtect(app)
    db.init_app(app)
    # In-memory counters are for one local process only; shared deployments
    # require a shared store and a carefully configured trusted proxy.
    limiter = Limiter(key_func=get_remote_address, app=app, storage_uri='memory://')
    login_manager = LoginManager(app)
    login_manager.login_view = 'signin'
    login_manager.session_protection = 'strong'
    login_manager.user_loader(auth.load_user)

    @app.before_request
    def enforce_idle_timeout():
        if request.endpoint == 'static' or not current_user.is_authenticated:
            return
        now = datetime.now(timezone.utc).timestamp()
        last = session.get('last_activity')
        if not isinstance(last, (int, float)) or now - last > 900:
            logout_user()
            session.clear()
        else:
            session['last_activity'] = now

    @app.after_request
    def security_headers(response):
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if request.endpoint in ('signin', 'signup', 'verify_email', 'resend_verification'):
            response.headers['Cache-Control'] = 'no-store'
        if request.endpoint == 'verify_email':
            response.headers['Referrer-Policy'] = 'no-referrer'
        if production:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    @app.errorhandler(CSRFError)
    def expired_form(_error):
        return render_template('form_expired.html'), 400

    @app.get('/')
    def landing():
        return render_template('landing.html')

    @app.route('/signin', methods=['GET', 'POST'])
    @limiter.limit('10 per minute', methods=['POST'])
    def signin():
        if request.method == 'POST':
            identifier = request.form.get('identifier', '')[:254]
            try:
                user = auth.authenticate(identifier, request.form.get('password', ''))
                if user:
                    session.clear()
                    login_user(user)
                    session.permanent = True
                    session['last_activity'] = datetime.now(timezone.utc).timestamp()
                    previous = user.previous_login_at
                    session['previous_login'] = previous.strftime('%d %b %Y, %H:%M UTC') if isinstance(previous, datetime) else None
                    audit.record('login_success', user.id)
                    return redirect(url_for({'student': 'student_home', 'staff': 'staff_home', 'admin': 'admin_home'}.get(user.role, 'account_home')))
                audit.record('login_failure')
            except (PyMongoError, RuntimeError):
                app.logger.warning('Sign-in database unavailable.')
                return render_template('signin.html', identifier=identifier,
                                       error='Sign-in is currently unavailable. Please try again later.'), 503
            return render_template('signin.html', identifier=identifier, error='The credentials could not be verified.'), 401
        return render_template('signin.html')

    @app.route('/signup', methods=['GET', 'POST'])
    @limiter.limit('5 per minute', methods=['POST'])
    def signup():
        if request.method == 'GET':
            return render_template('signup.html')
        values, errors = validate_signup(request.form)
        if errors:
            return render_template('signup.html', errors=errors, values=values), 400
        try:
            # Spend comparable password-hashing work before looking up a record.
            # The mailbox holder chooses the final password during confirmation.
            hash_password(request.form.get('password'))
            enrollment.register(values)
        except DuplicateKeyError:
            pass
        except (PyMongoError, RuntimeError):
            app.logger.warning('Account creation unavailable due to a database error.')
            return render_template('signup.html', values=values, errors={'service': 'Account creation is currently unavailable. Please try again later.'}), 503
        return render_template('signup.html', notice='If your details can be registered, your request has been received. Accounts require verification before use. Contact your university support team for help.')

    @app.route('/verify-email', methods=['GET', 'POST'])
    @limiter.limit('10 per minute', methods=['POST'])
    def verify_email():
        message = None
        retained_token = ''
        verified = False
        if request.method == 'POST':
            password = request.form.get('password', '')
            if validate_password(password) or password != request.form.get('confirm_password', ''):
                message = 'Choose matching passwords that meet the password requirements.'
                try:
                    retained_token = request.form.get('token', '')
                    tokens.token_hash(retained_token)
                except ValueError:
                    retained_token = ''
            else:
                try:
                    ok = enrollment.confirm(request.form.get('token', ''), password)
                except (PyMongoError, RuntimeError):
                    app.logger.warning('Email verification database unavailable.')
                    return render_template('verify_email.html', message='Verification is unavailable. Please try again later.'), 503
                message = 'Your account is ready to sign in.' if ok else 'This link is invalid or has expired.'
                verified = ok
        return render_template('verify_email.html', message=message, token=retained_token, verified=verified)

    @app.route('/resend-verification', methods=['GET', 'POST'])
    @limiter.limit('5 per minute', methods=['POST'])
    def resend_verification():
        notice = None
        if request.method == 'POST':
            raw = request.form.get('email', '')
            try:
                email = validate_email(raw, check_deliverability=False, allow_smtputf8=False).normalized.lower()
                enrollment.resend(email)
            except EmailNotValidError:
                pass
            except (PyMongoError, RuntimeError):
                app.logger.warning('Verification resend unavailable.')
            notice = 'If your account is eligible, a verification message will be sent.'
        return render_template('resend_verification.html', notice=notice)

    @app.get('/account')
    @login_required
    def account_home():
        return render_template('account_home.html')

    @app.get('/student/home')
    @role_required('student')
    def student_home():
        try:
            cases = case_service.get_student_cases(current_user)
        except (PyMongoError, RuntimeError):
            app.logger.warning('Student cases unavailable.')
            return render_template('student/home.html', cases=[], unavailable=True), 503
        return render_template('student/home.html', cases=cases)

    @app.route('/student/requests/new', methods=['GET', 'POST'])
    @role_required('student')
    def student_new_request():
        categories = [('Wellbeing', 'Talk about how you are feeling.'), ('Academic', 'Ask about study or coursework.'),
                      ('Financial', 'Share a money-related concern.'), ('Disability', 'Ask about disability or access needs.'),
                      ('Accommodation', 'Talk about housing or where you live.'), ('Something else', 'Tell us about another concern.')]
        errors, notice = {}, None
        if request.method == 'POST':
            category = request.form.get('category', '')
            description = request.form.get('description', '')
            if category not in {item[0] for item in categories}:
                errors['category'] = 'Choose the topic that feels closest.'
            if not description.strip() or len(description) > 3000:
                errors['description'] = 'Write a few words using no more than 3,000 characters.'
            if not errors:
                try:
                    reference = case_service.create_student_case(current_user, category, description,
                                                                 request.form.get('urgent') == 'yes')
                    return redirect(url_for('student_request_detail', reference=reference))
                except (PyMongoError, RuntimeError):
                    app.logger.warning('Student case creation unavailable.')
                    notice = 'We could not save your request. Please try again later.'
                    return render_template('student/new_request.html', categories=categories, errors=errors, notice=notice), 503
        return render_template('student/new_request.html', categories=categories, errors=errors, notice=notice), 400 if errors else 200

    @app.route('/student/requests/<reference>', methods=['GET', 'POST'])
    @role_required('student')
    def student_request_detail(reference):
        try:
            case = case_service.get_student_case(current_user, reference)
        except (PyMongoError, RuntimeError):
            app.logger.warning('Student case unavailable.')
            return 'Request temporarily unavailable.', 503
        if case is None:
            from flask import abort
            abort(404)
        notice, reply_error = None, None
        if request.method == 'POST':
            if case['status'] != 'Awaiting Student':
                from flask import abort
                abort(403)
            reply = request.form.get('reply', '')
            if not reply.strip() or len(reply) > 3000:
                reply_error = 'Write a reply using no more than 3,000 characters.'
            else:
                try:
                    if not case_service.add_student_reply(current_user, reference, reply):
                        from flask import abort
                        abort(409)
                    return redirect(url_for('student_request_detail', reference=reference))
                except (PyMongoError, RuntimeError):
                    app.logger.warning('Student reply unavailable.')
                    return 'Reply temporarily unavailable.', 503
        return render_template('student/detail.html', case=case, notice=notice, reply_error=reply_error), 400 if reply_error else 200

    def staff_filtered_cases(assigned_only=False):
        cases = case_service.staff_queue(current_user, assigned_only=assigned_only)
        query = request.args.get('q', '').strip()[:100].casefold()
        category = request.args.get('category', '')
        status = request.args.get('status', '')
        if query:
            cases = [case for case in cases if query in case['reference'].casefold()]
        if category in ('Personal support', 'Study support', 'Practical support', 'Other support'):
            cases = [case for case in cases if case['category_label'] == category]
        if status in ('Received', 'Assigned', 'In progress', 'Awaiting Student', 'Done'):
            cases = [case for case in cases if case['status'] == status]
        return cases

    @app.get('/staff/home')
    @role_required('staff')
    def staff_home():
        try:
            cases = staff_filtered_cases()
        except (PyMongoError, RuntimeError):
            app.logger.warning('Staff queue unavailable.')
            return 'Staff queue temporarily unavailable.', 503
        priority = {'Received': 0, 'Awaiting Student': 1, 'Assigned': 2, 'In progress': 3, 'Done': 4}
        cases.sort(key=lambda case: (not case['attention'] == 'Marked urgent', priority.get(case['status'], 5), -case['age_days']))
        return render_template('staff/home.html', cases=cases)

    @app.get('/staff/cases')
    @role_required('staff')
    def staff_cases():
        try:
            cases = staff_filtered_cases(assigned_only=True)
        except (PyMongoError, RuntimeError):
            app.logger.warning('Staff cases unavailable.')
            return 'Staff cases temporarily unavailable.', 503
        order = request.args.get('sort', 'oldest')
        if order == 'newest':
            cases.sort(key=lambda case: case['age_days'])
        elif order == 'reference':
            cases.sort(key=lambda case: case['reference'])
        else:
            cases.sort(key=lambda case: -case['age_days'])
        return render_template('staff/cases.html', cases=cases)

    @app.post('/staff/cases/<reference>/claim')
    @role_required('staff')
    def staff_claim_case(reference):
        try:
            if not case_service.claim_case(current_user, reference):
                return 'This request is no longer available to claim.', 409
            audit.record('case_claimed', current_user.id, case_reference=reference)
            return redirect(url_for('staff_case_detail', reference=reference))
        except (PyMongoError, RuntimeError):
            app.logger.warning('Case claim unavailable.')
            return 'Case claim temporarily unavailable.', 503

    @app.route('/staff/cases/<reference>', methods=['GET', 'POST'])
    @role_required('staff')
    def staff_case_detail(reference):
        from flask import abort
        try:
            # Never return a case belonging to another officer, including on POST.
            case = case_service.get_staff_case(current_user, reference)
            if case is None:
                abort(404)
            if request.method == 'POST':
                action = request.form.get('action', '')
                value = request.form.get('status' if action == 'status' else action, '')
                try:
                    updated = case_service.update_staff_case(current_user, reference, action, value)
                except ValueError:
                    abort(400)
                if not updated:
                    abort(404)
                audit.record('case_' + action, current_user.id, case_reference=reference)
                return redirect(url_for('staff_cases' if action == 'archive' else 'staff_case_detail',
                                        **({} if action == 'archive' else {'reference': reference})))
            return render_template('staff/detail.html', case=case)
        except (PyMongoError, RuntimeError):
            app.logger.warning('Staff case unavailable.')
            return 'Case temporarily unavailable.', 503

    @app.get('/admin/home')
    @role_required('admin')
    def admin_home():
        try:
            return render_template('admin/home.html', overview=stats.get_admin_overview(current_user))
        except (PyMongoError, RuntimeError):
            app.logger.warning('Case statistics unavailable.')
            return 'Case statistics temporarily unavailable.', 503

    @app.get('/admin/users')
    @role_required('admin')
    def admin_users():
        try:
            return render_template('admin/users.html', users=user_admin.list_users(current_user))
        except (PyMongoError, RuntimeError):
            app.logger.warning('Account management unavailable.')
            return 'Account management temporarily unavailable.', 503

    def admin_change_user(target, action):
        from flask import abort
        value = request.form.get('status' if action == 'status' else 'role', '')
        try:
            try:
                event, target_id, old_role, new_role = user_admin.change_user(current_user, target, action, value)
            except ValueError:
                audit.record('admin_action_denied', current_user.id)
                abort(400)
            except PermissionError:
                audit.record('admin_action_denied', current_user.id)
                return 'This account change is not permitted.', 403
            audit.record(event, current_user.id, target_id=target_id,
                         old_role=old_role if new_role else None, new_role=new_role)
            return redirect(url_for('admin_users'))
        except (PyMongoError, RuntimeError):
            app.logger.warning('Account management unavailable.')
            return 'Account management temporarily unavailable.', 503

    @app.post('/admin/users/<target>/status')
    @role_required('admin')
    def admin_user_status(target):
        return admin_change_user(target, 'status')

    @app.post('/admin/users/<target>/role')
    @role_required('admin')
    def admin_user_role(target):
        return admin_change_user(target, 'role')

    @app.get('/admin/audit')
    @role_required('admin')
    def admin_audit():
        try:
            events, page, has_next = audit_viewer.get_events(current_user, request.args)
        except (PyMongoError, RuntimeError):
            app.logger.warning('Audit viewer unavailable.')
            return 'Audit activity temporarily unavailable.', 503
        return render_template('admin/audit.html', events=events, event_types=audit_viewer.EVENTS,
                               page=page, has_next=has_next)

    @app.post('/logout')
    @login_required
    def logout():
        audit.record('logout', current_user.id)
        logout_user()
        session.clear()
        return redirect(url_for('landing'))

    return app
