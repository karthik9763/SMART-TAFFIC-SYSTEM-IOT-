import json
import unittest
from app import app, db
from database import User
from werkzeug.security import check_password_hash

class AuthIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI='sqlite://',
            DEVICE_MINIMUM_INTERVAL_SECONDS=0,
            JWT_SECRET='test-jwt-secret-key-at-least-32-chars-long'
        )

    def setUp(self):
        with app.app_context():
            db.create_all()
            User.query.filter(User.username.in_(['traffic_analyst', 'admin_two', 'operator_bob'])).delete()
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                admin = User(username='admin', email='admin@example.com', role='Admin')
                db.session.add(admin)
            else:
                admin.email = 'admin@example.com'
            admin.set_password('AdminSecret123!')
            db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        with app.app_context():
            User.query.filter(User.username.in_(['traffic_analyst', 'admin_two', 'operator_bob'])).delete()
            admin = User.query.filter_by(username='admin').first()
            if admin:
                admin.email = 'admin@smarttraffic.ai'
                admin.set_password('123456')
            db.session.commit()
            db.session.remove()


    def test_json_registration_success(self):
        response = self.client.post('/api/auth/register', json={
            'username': 'traffic_analyst',
            'email': 'analyst@traffic.local',
            'password': 'SecurePassword456!',
            'confirm_password': 'SecurePassword456!'
        })
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('token', data)
        self.assertEqual(data['user']['username'], 'traffic_analyst')
        self.assertEqual(data['user']['email'], 'analyst@traffic.local')

        # Verify persisted in database with hashed password
        with app.app_context():
            saved = User.query.filter_by(username='traffic_analyst').first()
            self.assertIsNotNone(saved)
            self.assertTrue(saved.check_password('SecurePassword456!'))
            self.assertNotEqual(saved.password_hash, 'SecurePassword456!')

    def test_json_registration_duplicate_username_and_email(self):
        # Duplicate username
        res1 = self.client.post('/api/auth/register', json={
            'username': 'admin',
            'email': 'new_admin@example.com',
            'password': 'Password123!'
        })
        self.assertEqual(res1.status_code, 409)
        self.assertIn('Username already exists', res1.get_json()['message'])

        # Duplicate email with different casing
        res2 = self.client.post('/api/auth/register', json={
            'username': 'admin_two',
            'email': 'ADMIN@EXAMPLE.COM',
            'password': 'Password123!'
        })
        self.assertEqual(res2.status_code, 409)
        self.assertIn('Email already exists', res2.get_json()['message'])

    def test_json_registration_validation_errors(self):
        # Short password
        res = self.client.post('/api/auth/register', json={
            'username': 'operator_bob',
            'email': 'bob@traffic.org',
            'password': '123'
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('at least 6 characters', res.get_json()['message'])

        # Invalid email
        res2 = self.client.post('/api/auth/register', json={
            'username': 'operator_bob',
            'email': 'not-an-email',
            'password': 'Password123!'
        })
        self.assertEqual(res2.status_code, 400)
        self.assertIn('valid email address', res2.get_json()['message'])

    def test_json_login_by_username_and_email(self):
        # Login with username
        res1 = self.client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'AdminSecret123!'
        })
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        self.assertEqual(data1['status'], 'success')
        self.assertIn('token', data1)
        self.assertIn('csrf_token', data1)
        self.assertEqual(data1['user']['username'], 'admin')

        # Login with email and whitespace / uppercase
        res2 = self.client.post('/api/auth/login', json={
            'username': '  ADMIN@EXAMPLE.COM  ',
            'password': 'AdminSecret123!'
        })
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        self.assertEqual(data2['status'], 'success')
        self.assertEqual(data2['user']['username'], 'admin')

    def test_json_login_wrong_password(self):
        res = self.client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'WrongPassword!'
        })
        self.assertEqual(res.status_code, 401)
        self.assertIn('Wrong password', res.get_json()['message'])

    def test_json_login_user_not_found(self):
        res = self.client.post('/api/auth/login', json={
            'username': 'non_existent_user',
            'password': 'AnyPassword123!'
        })
        self.assertEqual(res.status_code, 404)
        self.assertIn('User not found', res.get_json()['message'])

    def test_jwt_bearer_protected_api(self):
        # Login to obtain token
        login_res = self.client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'AdminSecret123!'
        })
        token = login_res.get_json()['token']

        # Access /api/auth/me with Bearer token in a fresh client (no session cookie)
        fresh_client = app.test_client()
        session_res = fresh_client.get('/api/auth/me', headers={
            'Authorization': f'Bearer {token}'
        })
        self.assertEqual(session_res.status_code, 200)
        data = session_res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['user']['username'], 'admin')


    def test_unauthenticated_api_returns_401(self):
        res = self.client.get('/api/auth/session')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json()['status'], 'error')

    def test_browser_form_login_and_logout(self):
        # Submit HTML form
        res = self.client.post('/login', data={
            'username': 'admin',
            'password': 'AdminSecret123!'
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/dashboard', res.headers['Location'])

        # Logout
        logout_res = self.client.post('/logout', follow_redirects=False)
        self.assertEqual(logout_res.status_code, 302)
        self.assertIn('/login', logout_res.headers['Location'])

if __name__ == '__main__':
    unittest.main()
