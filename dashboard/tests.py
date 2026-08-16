import json
from datetime import timedelta
from io import BytesIO
from os import makedirs
from os.path import join
from shutil import copyfile, rmtree
from tempfile import mkdtemp
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import empty

from accounts.models import User
from dashboard.views import _dashboard_stats
from journals.models import Journal, Manuscript, ManuscriptStatus
from projects.models import (
    MemberRole, Milestone, Project, ProjectApplication, ProjectMembership,
    ReviewStatus, Task, TaskPriority, TaskStatus,
)


MANIFEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'gfr.staticfiles.ResilientManifestStaticFilesStorage'},
}


@override_settings(DEBUG=False, STORAGES=MANIFEST_STORAGES)
class UncollectedStaticFilesTests(TestCase):
    """The dashboard must render even when collectstatic has not run."""

    def setUp(self):
        # Mirrors a server where collectstatic copied the files but never wrote
        # a manifest, which is what happens when it runs under local settings.
        root = mkdtemp()
        self.addCleanup(rmtree, root, True)
        makedirs(join(root, 'img'))
        copyfile(
            join(settings.BASE_DIR, 'static', 'img', 'sandy-mascot.png'),
            join(root, 'img', 'sandy-mascot.png'),
        )
        overrides = override_settings(STATIC_ROOT=root)
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
        self.assertContains(response, 'Chat, start a project, or leave a review.')
        self.assertContains(response, 'Chat with Sandy')
        self.assertContains(response, 'Leave a review')
        self.assertContains(response, reverse('dashboard:sandy_chat'))
        self.assertContains(response, reverse('dashboard:sandy_project_draft'))
        # Both entry points are visible before the panel opens.
        self.assertContains(response, 'data-sandy-quick="chat"')
        self.assertContains(response, 'data-sandy-quick="review"')
        # Default seeded role cannot create projects, so Project stays hidden.
        self.assertNotContains(response, 'data-sandy-quick="project"')
        self.assertContains(response, 'img/sandy-mascot.png')
        # The chat shows Sandy's avatar next to her messages.
        self.assertContains(response, 'data-sandy-avatar=')

    def test_guarantor_sees_sandy_project_action(self):
        guarantor = User.objects.create_user(
            username='guarantor',
            email='guarantor@example.com',
            password='StrongTestPassword!9',
            role='professor',
        )
        self.client.force_login(guarantor)
        response = self.client.get(reverse('dashboard:home'))
        self.assertContains(response, 'data-sandy-quick="project"')
        self.assertContains(response, 'Create a project')
        self.assertContains(response, 'data-can-create-project="1"')

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


def _http_error(code, payload):
    """An HTTPError carrying a Gemini-shaped JSON error body."""
    return HTTPError(
        url='https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent',
        code=code,
        msg='error',
        hdrs=None,
        fp=BytesIO(json.dumps(payload).encode('utf-8')),
    )


@override_settings(GEMINI_API_KEY='test-gemini-key', GEMINI_MODEL='gemini-3.6-flash')
class SandyChatTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='chatty',
            email='chatty@example.com',
            password='StrongTestPassword!9',
            first_name='Lena',
            last_name='Vogel',
            role='researcher',
        )
        self.client.force_login(self.user)
        self.url = reverse('dashboard:sandy_chat')

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_empty_message_is_rejected(self):
        response = self._post({'message': '  '})
        self.assertEqual(response.status_code, 400)

    @override_settings(GEMINI_API_KEY='')
    def test_missing_api_key_is_a_clear_service_error(self):
        response = self._post({'message': 'How do I submit a paper?'})
        self.assertEqual(response.status_code, 503)

    @patch('dashboard.views.urlopen')
    def test_chat_forwards_message_with_platform_context(self, mock_urlopen):
        upstream = MagicMock()
        upstream.read.return_value = json.dumps({
            'candidates': [{
                'content': {'parts': [{'text': 'Researchers can submit from Journals.'}]},
            }],
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = upstream

        response = self._post({
            'message': 'Can I submit a manuscript?',
            'history': [{'role': 'user', 'text': 'Hi'}, {'role': 'model', 'text': 'Hello!'}],
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['reply'], 'Researchers can submit from Journals.')
        request = mock_urlopen.call_args.args[0]
        self.assertIn('generativelanguage.googleapis.com', request.full_url)
        # The key must travel as a header so it cannot leak through URLs or logs.
        self.assertNotIn('test-gemini-key', request.full_url)
        self.assertEqual(request.headers['X-goog-api-key'], 'test-gemini-key')
        body = json.loads(request.data)
        system_text = body['systemInstruction']['parts'][0]['text']
        self.assertIn('Global Forum for Researchers', system_text)
        # Sandy is a female AI assistant, not the old beaver mascot.
        self.assertNotIn('beaver', system_text.lower())
        self.assertIn('Lena Vogel', system_text)
        self.assertIn('Researcher', system_text)
        self.assertIn('submit manuscripts', system_text)
        self.assertEqual(body['contents'][-1]['parts'][0]['text'], 'Can I submit a manuscript?')
        self.assertEqual(request.headers['User-agent'], 'GFR-Sandy/1.0')
        # Gemini 3 spends maxOutputTokens on reasoning before it writes anything,
        # so the budget has to cover both or the reply comes back empty.
        self.assertEqual(body['generationConfig']['thinkingConfig']['thinkingLevel'], 'minimal')
        self.assertGreaterEqual(body['generationConfig']['maxOutputTokens'], 2048)
        self.assertNotIn('temperature', body['generationConfig'])

    @patch('dashboard.views.urlopen')
    def test_reply_exhausted_by_reasoning_is_logged_with_its_finish_reason(self, mock_urlopen):
        upstream = MagicMock()
        upstream.read.return_value = json.dumps({
            'candidates': [{'content': {}, 'finishReason': 'MAX_TOKENS'}],
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = upstream

        with self.assertLogs('dashboard.views', level='WARNING') as logs:
            response = self._post({'message': 'Hello'})

        self.assertEqual(response.status_code, 502)
        self.assertIn('MAX_TOKENS', '\n'.join(logs.output))

    @patch('dashboard.views.urlopen', side_effect=URLError('offline'))
    def test_upstream_failure_returns_service_error(self, _mock_urlopen):
        response = self._post({'message': 'Hello'})
        self.assertEqual(response.status_code, 502)

    @patch('dashboard.views.urlopen')
    def test_rejected_key_is_logged_with_the_reason_from_gemini(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(400, {
            'error': {'message': 'API key not valid. Please pass a valid API key.'},
        })

        with self.assertLogs('dashboard.views', level='WARNING') as logs:
            response = self._post({'message': 'Hello'})

        self.assertEqual(response.status_code, 502)
        self.assertIn('API key not valid', '\n'.join(logs.output))

    @patch('dashboard.views.urlopen')
    def test_exhausted_quota_asks_the_user_to_retry_later(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(429, {
            'error': {'message': 'Quota exceeded for quota metric.'},
        })

        with self.assertLogs('dashboard.views', level='WARNING'):
            response = self._post({'message': 'Hello'})

        self.assertEqual(response.status_code, 429)
        self.assertIn('try again in a minute', response.json()['error'])

    @patch('dashboard.views.urlopen')
    def test_blocked_prompt_is_logged_with_its_reason(self, mock_urlopen):
        upstream = MagicMock()
        upstream.read.return_value = json.dumps({
            'promptFeedback': {'blockReason': 'SAFETY'},
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = upstream

        with self.assertLogs('dashboard.views', level='WARNING') as logs:
            response = self._post({'message': 'Hello'})

        self.assertEqual(response.status_code, 502)
        self.assertIn('SAFETY', '\n'.join(logs.output))

    def test_login_is_required(self):
        self.client.logout()
        response = self._post({'message': 'Hello'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])


class DashboardStatsTests(TestCase):
    """Overview cards must pair each number with a sparkline from the same queryset."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='stats_user',
            email='stats@example.com',
            password='StrongTestPassword!9',
        )
        self.journal = Journal.objects.create(
            name='Test Journal',
            slug='test-journal',
            description='A journal for tests.',
        )

    def test_overview_has_three_cards_and_no_unread_messages_card(self):
        stats = _dashboard_stats(self.user)
        self.assertEqual(
            [s['label'] for s in stats],
            ['Manuscripts', 'Projects', 'Open tasks'],
        )

    def test_manuscript_line_chart_counts_only_recent_records(self):
        recent = Manuscript.objects.create(
            journal=self.journal, submitter=self.user,
            title='Recent study', abstract='x',
            status=ManuscriptStatus.SUBMITTED,
        )
        Manuscript.objects.filter(pk=recent.pk).update(
            created_at=timezone.now() - timedelta(days=2),
        )
        old = Manuscript.objects.create(
            journal=self.journal, submitter=self.user,
            title='Old study', abstract='y',
            status=ManuscriptStatus.SUBMITTED,
        )
        Manuscript.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=30),
        )
        draft = Manuscript.objects.create(
            journal=self.journal, submitter=self.user,
            title='Draft', abstract='z',
        )
        Manuscript.objects.filter(pk=draft.pk).update(
            created_at=timezone.now() - timedelta(days=2),
        )

        card = _dashboard_stats(self.user)[0]
        self.assertEqual(card['value'], 2)                # DRAFT excluded
        pts = card['chart']['points']
        self.assertEqual(len(pts), 7)
        self.assertEqual(sum(p['n'] for p in pts), 1)
        self.assertEqual(pts[-3]['n'], 1)                 # counted on its day
        self.assertIn('chart_json', card)
        self.assertIn('chart', card)
        self.assertTrue(card['chart']['path'].startswith('M'))

    def test_line_chart_is_flat_when_there_is_no_activity(self):
        stats = _dashboard_stats(self.user)
        for stat in stats:
            pts = stat['chart']['points']
            self.assertTrue(all(p['n'] == 0 for p in pts))

    def test_projects_and_tasks_cards_share_their_line_chart_source(self):
        project = Project.objects.create(
            title='Research project', description='About',
            created_by=self.user,
        )
        project.members.add(self.user)
        Project.objects.filter(pk=project.pk).update(
            created_at=timezone.now() - timedelta(days=3),
        )
        Task.objects.create(project=project, title='Draft report', assigned_to=self.user)
        Task.objects.create(
            project=project, title='Analyse data', assigned_to=self.user,
            status=TaskStatus.DONE,
        )

        projects_card, tasks_card = _dashboard_stats(self.user)[1], _dashboard_stats(self.user)[2]
        self.assertEqual(projects_card['value'], 1)
        self.assertEqual(sum(p['n'] for p in projects_card['chart']['points']), 1)
        self.assertEqual(tasks_card['value'], 1)
        self.assertEqual(sum(p['n'] for p in tasks_card['chart']['points']), 1)
        self.assertIn('Research project', projects_card['chart']['points'][-4]['t'])

    def test_line_charts_share_one_global_visual_scale(self):
        """When one card has a higher peak, its line must reach higher
        than a card with a lower peak — all three share a single scale."""
        for _ in range(3):
            m = Manuscript.objects.create(
                journal=self.journal, submitter=self.user,
                title='Three studies', abstract='x',
                status=ManuscriptStatus.SUBMITTED,
            )
            Manuscript.objects.filter(pk=m.pk).update(
                created_at=timezone.now() - timedelta(days=1),
            )
        project = Project.objects.create(
            title='Project', description='About',
            created_by=self.user,
        )
        project.members.add(self.user)
        Task.objects.create(project=project, title='One task', assigned_to=self.user)

        stats = _dashboard_stats(self.user)
        ms_pts = stats[0]['chart']['points']     # manuscripts: peak = 3
        tasks_pts = stats[2]['chart']['points']  # open tasks:  peak = 1

        ms_min_y = min(p['y'] for p in ms_pts)
        tasks_min_y = min(p['y'] for p in tasks_pts)
        self.assertLess(ms_min_y, tasks_min_y)   # peak 3 higher than peak 1
        self.assertEqual(stats[0]['chart']['y_max'], 3)

    def test_card_height_grows_when_y_max_exceeds_six(self):
        """When y_max > 6 the SVG should be taller than the default 80px."""
        for _ in range(7):
            m = Manuscript.objects.create(
                journal=self.journal, submitter=self.user,
                title='Study', abstract='x',
                status=ManuscriptStatus.SUBMITTED,
            )
            Manuscript.objects.filter(pk=m.pk).update(
                created_at=timezone.now() - timedelta(days=1),
            )
        stats = _dashboard_stats(self.user)
        chart = stats[0]['chart']
        self.assertEqual(chart['y_max'], 7)
        self.assertGreater(chart['svg_h'], 80)
        self.assertEqual(chart['svg_h'], 20 + 7 * 10)  # = 90


class PendingOwnerWorkTests(TestCase):
    """The dashboard shows a pending-work section to project owners and
    managers only, and hides it entirely when there is nothing to review."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='proj_owner', email='owner@example.com',
            password='StrongTestPassword!9',
        )
        self.member = User.objects.create_user(
            username='plain_member', email='member@example.com',
            password='StrongTestPassword!9',
        )
        self.applicant = User.objects.create_user(
            username='wannabe', email='wannabe@example.com',
            password='StrongTestPassword!9',
        )
        self.project = Project.objects.create(
            title='Quantum study', description='About', created_by=self.owner,
        )
        ProjectMembership.objects.create(
            project=self.project, user=self.owner, role=MemberRole.OWNER,
        )
        self.url = reverse('dashboard:home')

    def _add_pending_work(self):
        ProjectMembership.objects.create(
            project=self.project, user=self.member, role=MemberRole.MEMBER,
        )
        ProjectApplication.objects.create(
            project=self.project, applicant=self.applicant, message='Let me join',
        )
        Task.objects.create(
            project=self.project, title='Write the report',
            assigned_to=self.member,
            submission_note='Draft ready', status=TaskStatus.IN_PROGRESS,
            review_status=ReviewStatus.SUBMITTED,
        )

    def test_owner_sees_pending_applications_and_tasks(self):
        self._add_pending_work()
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertContains(response, 'Pending work in your projects')
        self.assertContains(response, 'Quantum study')
        self.assertContains(response, 'Let me join')
        self.assertContains(response, 'Write the report')
        self.assertContains(response, '>2<')

    def test_manager_sees_the_section_too(self):
        self._add_pending_work()
        ProjectMembership.objects.filter(project=self.project, user=self.member).update(
            role=MemberRole.MANAGER,
        )
        self.client.force_login(self.member)
        response = self.client.get(self.url)
        self.assertContains(response, 'Pending work in your projects')

    def test_plain_member_does_not_see_the_section(self):
        self._add_pending_work()
        self.client.force_login(self.member)
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Pending work in your projects')

    def test_user_without_projects_does_not_see_the_section(self):
        self._add_pending_work()
        outsider = User.objects.create_user(
            username='outsider', email='outsider@example.com',
            password='StrongTestPassword!9',
        )
        self.client.force_login(outsider)
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Pending work in your projects')

    def test_owner_without_pending_work_sees_no_empty_section(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Pending work in your projects')

    def test_reviewed_items_disappear_from_the_section(self):
        self._add_pending_work()
        Task.objects.filter(project=self.project).update(
            review_status=ReviewStatus.APPROVED, status=TaskStatus.DONE,
        )
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Write the report')
        self.assertContains(response, 'Pending work in your projects')
        self.assertContains(response, '>1<')

    def test_pending_section_groups_by_project(self):
        self._add_pending_work()
        project2 = Project.objects.create(
            title='AI research', description='About AI', created_by=self.owner,
        )
        ProjectMembership.objects.create(
            project=project2, user=self.owner, role=MemberRole.OWNER,
        )
        Task.objects.create(
            project=project2, title='Build prototype',
            assigned_to=self.member, status=TaskStatus.IN_PROGRESS,
            review_status=ReviewStatus.SUBMITTED,
        )
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertContains(response, 'Quantum study')
        self.assertContains(response, 'AI research')
        self.assertContains(response, 'Write the report')
        self.assertContains(response, 'Build prototype')
        self.assertContains(response, f'data-pending-project="{self.project.slug}"')
        self.assertContains(response, f'data-pending-project="{project2.slug}"')

    def test_pending_section_shows_priority_badges(self):
        self._add_pending_work()
        Task.objects.filter(project=self.project, title='Write the report').update(
            priority=TaskPriority.HIGH,
        )
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertContains(response, 'high')

    def test_pending_section_shows_overdue_tasks(self):
        self._add_pending_work()
        from datetime import date
        Task.objects.filter(project=self.project, title='Write the report').update(
            due_date=date(2020, 1, 1),
        )
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertContains(response, 'overdue')

    def test_pending_section_shows_milestones(self):
        self._add_pending_work()
        Milestone.objects.create(
            project=self.project, title='Final review',
            due_date=timezone.localdate(),
        )
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertContains(response, 'Final review')
        self.assertContains(response, 'Milestones')

    def test_overdue_milestone_appears_in_section(self):
        self._add_pending_work()
        from datetime import date
        Milestone.objects.create(
            project=self.project, title='Past deadline',
            due_date=date(2020, 6, 1),
        )
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertContains(response, 'Past deadline')
        self.assertContains(response, 'overdue')
