import json
from shutil import rmtree
from tempfile import mkdtemp
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.functional import empty

from accounts.models import User


MANIFEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'gfr.staticfiles.ResilientManifestStaticFilesStorage'},
}


@override_settings(DEBUG=False, STORAGES=MANIFEST_STORAGES)
class UncollectedStaticFilesTests(TestCase):
    """The dashboard must render even when collectstatic has not run."""

    def setUp(self):
        empty_root = mkdtemp()
        self.addCleanup(rmtree, empty_root, True)
        overrides = override_settings(STATIC_ROOT=empty_root)
        overrides.enable()
        self.addCleanup(overrides.disable)

        self.user = User.objects.create_user(
            username='fresh',
            email='fresh@example.com',
            password='StrongTestPassword!9',
        )
        self.client.force_login(self.user)
        staticfiles_storage._wrapped = empty
        self.addCleanup(setattr, staticfiles_storage, '_wrapped', empty)

    def test_dashboard_renders_without_a_staticfiles_manifest(self):
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)

    def test_missing_asset_falls_back_to_the_unhashed_path(self):
        self.assertEqual(
            staticfiles_storage.url('img/sandy-mascot.png'),
            '/static/img/sandy-mascot.png',
        )


@override_settings(SANDY_FEEDBACK_WEBHOOK_URL='https://example.test/feedback')
class SandyFeedbackTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='reviewer',
            email='reviewer@example.com',
            password='StrongTestPassword!9',
            first_name='Sandy',
            last_name='Tester',
        )
        self.client.force_login(self.user)
        self.url = reverse('dashboard:sandy_feedback')

    def test_dashboard_includes_sandy_widget(self):
        response = self.client.get(reverse('dashboard:home'))
        self.assertContains(response, 'id="sandy-widget"')
        self.assertContains(response, 'Please give us your review here.')

    def test_rating_is_required_and_validated(self):
        response = self.client.post(self.url, {'rating': '8'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Please choose a rating from 1 to 5.')

    @patch('dashboard.views.urlopen')
    def test_feedback_is_forwarded_as_json(self, mock_urlopen):
        upstream = MagicMock(status=200)
        mock_urlopen.return_value.__enter__.return_value = upstream

        response = self.client.post(self.url, {
            'rating': '5',
            'bugs': 'No bugs',
            'features': 'Dark mode',
        })

        self.assertEqual(response.status_code, 200)
        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload['rating'], 5)
        self.assertEqual(payload['bugs'], 'No bugs')
        self.assertEqual(payload['requested_features'], 'Dark mode')
        self.assertEqual(payload['user']['username'], self.user.username)
        self.assertNotIn('email', payload['user'])
        self.assertNotIn('password', payload['user'])
        self.assertEqual(request.headers['Content-type'], 'application/json')
        self.assertEqual(request.headers['User-agent'], 'GFR-Sandy/1.0')

    @override_settings(SANDY_FEEDBACK_WEBHOOK_URL='')
    def test_missing_webhook_is_a_clear_service_error(self):
        response = self.client.post(self.url, {'rating': '4'})
        self.assertEqual(response.status_code, 503)

    @patch('dashboard.views.urlopen', side_effect=URLError('offline'))
    def test_upstream_failure_returns_service_error(self, _mock_urlopen):
        response = self.client.post(self.url, {'rating': '4'})
        self.assertEqual(response.status_code, 502)

    def test_login_is_required(self):
        self.client.logout()
        response = self.client.post(self.url, {'rating': '4'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])
