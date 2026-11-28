"""Opt-in real-browser journeys against a disposable local MongoDB database."""
import os
import threading
import uuid
from unittest.mock import patch

import pytest
from bson import ObjectId
from pymongo import MongoClient
from werkzeug.serving import make_server

from app import create_app
from services import cases
from services.auth import User
from services.passwords import hash_password


@pytest.fixture
def browser_app():
    if os.environ.get('RUN_BROWSER_TESTS') != '1':
        pytest.skip('Set RUN_BROWSER_TESTS=1 to run the local browser journeys.')
    uri = os.environ.get('TEST_MONGODB_URI')
    if not uri:
        pytest.skip('Set TEST_MONGODB_URI to an isolated test MongoDB identity.')
    sync_api = pytest.importorskip('playwright.sync_api')
    mongo = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=3000)
    name = 'unidays_test_browser_' + uuid.uuid4().hex
    database = mongo[name]
    with patch('db.init_app'):
        app = create_app()
    app.config.update(TESTING=True, CASES_DB=name, MONGODB_AUTH_DB=name, MONGODB_AUDIT_DB=name)
    app.extensions.update(mongodb=mongo, cases_mongodb=mongo, audit_writer=mongo)
    password = 'fictional browser test passphrase'
    password_hash = hash_password(password)
    users = {}
    for identity, role in [('student-one', 'student'), ('student-two', 'student'), ('staff', 'staff')]:
        user = {'_id': ObjectId(), 'role': role, 'email': identity + '@example.edu',
                'full_name': 'Fictional ' + identity, 'password_hash': password_hash,
                'is_active': True, 'failed_login_count': 0}
        database.users.insert_one(user)
        users[identity] = user
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_api.sync_playwright() as playwright:
            # Allow an existing local Chromium/Chrome; otherwise use Playwright's browser.
            browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE'))
            try:
                yield app, database, users, password, browser, f'http://127.0.0.1:{server.server_port}'
            finally:
                browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        mongo.drop_database(name)
        mongo.close()


def sign_in(page, base, account, password):
    page.goto(base + '/signin')
    page.locator('#identifier').fill(account['email'])
    page.locator('#password').fill(password)
    page.locator('form button[type="submit"]').click()


def test_browser_student_creates_and_views_request(browser_app):
    app, database, users, password, browser, base = browser_app
    page = browser.new_page()
    sign_in(page, base, users['student-one'], password)
    assert page.url.endswith('/student/home')
    page.goto(base + '/student/requests/new')
    page.locator('input[name="category"][value="Academic"]').check()
    page.locator('#description').fill('Fictional browser request')
    page.get_by_role('button', name='Save request').click()
    assert '/student/requests/' in page.url
    assert page.get_by_text('Fictional browser request').is_visible()
    record = database.cases.find_one({'owner_id': users['student-one']['_id']})
    assert record['status'] == 'New'
    assert 'Fictional browser request' not in repr(record)
    page.close()


def test_browser_student_cannot_open_another_students_case(browser_app):
    app, _, users, password, browser, base = browser_app
    with app.app_context():
        reference = cases.create_student_case(User(users['student-one']), 'Academic', 'Private example', False)
    page = browser.new_page()
    sign_in(page, base, users['student-two'], password)
    response = page.goto(base + '/student/requests/' + reference)
    assert response.status == 404
    assert 'Private example' not in page.content()
    page.close()


def test_browser_staff_note_does_not_reach_student(browser_app):
    app, _, users, password, browser, base = browser_app
    with app.app_context():
        reference = cases.create_student_case(User(users['student-one']), 'Academic', 'Student example', False)
    staff = browser.new_page()
    sign_in(staff, base, users['staff'], password)
    row = staff.locator('article.staff-case-row').filter(has_text=reference)
    row.get_by_role('button', name='Claim request').click()
    staff.locator('#note').fill('Private browser note')
    staff.get_by_role('button', name='Save note').click()
    staff.goto(base + '/staff/cases/' + reference)
    assert staff.get_by_text('Private browser note').is_visible()
    student = browser.new_page()
    sign_in(student, base, users['student-one'], password)
    student.goto(base + '/student/requests/' + reference)
    assert student.get_by_text('Student example').is_visible()
    assert 'Private browser note' not in student.content()
    staff.close()
    student.close()
