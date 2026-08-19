import json

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from messaging.utils import get_or_create_project_chat
from .models import (
    InvitationStatus, MemberRole, Project, ProjectApplication, ProjectInvitation,
    ProjectMembership, ProjectSection, ProjectStatus, ReviewStatus, Task, TaskStatus,
)


class GuarantorWorkflowTests(TestCase):
    def setUp(self):
        self.guarantor = User.objects.create_user('guarantor', 'g@example.com', 'password', role=Role.PROFESSOR)
        self.applicant = User.objects.create_user('applicant', 'a@example.com', 'password', role=Role.RESEARCHER)
        self.project = Project.objects.create(title='Structured study', description='A study', created_by=self.guarantor)
        ProjectMembership.objects.create(project=self.project, user=self.guarantor, role=MemberRole.OWNER)

    def test_application_requires_guarantor_acceptance_before_membership(self):
        self.client.force_login(self.applicant)
        response = self.client.post(reverse('dashboard:project_join', args=[self.project.slug]), {
            'message': 'I work in this area.', 'answer': 'I can analyse the data.',
        })
        self.assertRedirects(response, reverse('dashboard:project_detail', args=[self.project.slug]))
        application = ProjectApplication.objects.get(project=self.project, applicant=self.applicant)
        self.assertEqual(application.status, ProjectApplication.Status.PENDING)
        self.assertFalse(ProjectMembership.objects.filter(project=self.project, user=self.applicant).exists())

        self.client.force_login(self.guarantor)
        self.client.post(reverse('dashboard:project_review_application', args=[self.project.slug, application.pk, 'accept']))
        self.assertTrue(ProjectMembership.objects.filter(project=self.project, user=self.applicant).exists())
        application.refresh_from_db()
        self.assertEqual(application.status, ProjectApplication.Status.ACCEPTED)

    def test_task_belongs_to_a_guarantor_section(self):
        section = ProjectSection.objects.create(project=self.project, title='Data collection', order=1)
        task = Task.objects.create(project=self.project, section=section, title='Collect sources')
        self.assertEqual(task.section.title, 'Data collection')


class ProjectCanvasTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('canvas-owner', 'owner@example.com', 'password', role=Role.PROFESSOR)
        self.member = User.objects.create_user('canvas-member', 'member@example.com', 'password', role=Role.RESEARCHER)
        self.outsider = User.objects.create_user('canvas-outsider', 'outsider@example.com', 'password', role=Role.RESEARCHER)
        self.project = Project.objects.create(title='Canvas study', description='A map of our work.', created_by=self.owner)
        self.owner_membership = ProjectMembership.objects.create(project=self.project, user=self.owner, role=MemberRole.OWNER)
        self.member_membership = ProjectMembership.objects.create(project=self.project, user=self.member, role=MemberRole.MEMBER)
        self.task = Task.objects.create(project=self.project, title='Map the cohort', assigned_to=self.member, status=TaskStatus.IN_PROGRESS)

    def test_canvas_is_member_only_and_contains_owner_and_work(self):
        canvas_url = reverse('dashboard:project_canvas', args=[self.project.slug])
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(canvas_url).status_code, 404)

        self.client.force_login(self.owner)
        response = self.client.get(canvas_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Project Canvas')
        self.assertContains(response, 'canvas-owner')
        self.assertContains(response, 'Map the cohort')

    def test_canvas_position_is_saved_for_project_members_only(self):
        url = reverse('dashboard:project_canvas_position', args=[self.project.slug, self.member.pk])
        self.client.force_login(self.member)
        response = self.client.post(url, data=json.dumps({'x': 31.5, 'y': 68.25}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.canvas_x, 31.5)
        self.assertEqual(self.member_membership.canvas_y, 68.25)

        owner_url = reverse('dashboard:project_canvas_position', args=[self.project.slug, self.owner.pk])
        response = self.client.post(owner_url, data=json.dumps({'x': 44, 'y': 52}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.canvas_x, 44)

        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(url, data=json.dumps({'x': 45, 'y': 50}), content_type='application/json').status_code, 404)

    def test_canvas_payload_marks_viewer_and_exposes_project_position(self):
        data_url = reverse('dashboard:project_canvas_data', args=[self.project.slug])
        self.client.force_login(self.member)
        payload = self.client.get(data_url).json()
        by_id = {item['id']: item for item in payload['members']}
        self.assertTrue(by_id[self.member.pk]['is_current_user'])
        self.assertFalse(by_id[self.owner.pk]['is_current_user'])
        self.assertEqual(payload['project']['position'], {'x': None, 'y': None})

        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(data_url).status_code, 404)

    def test_project_hub_position_is_saved_and_clamped(self):
        url = reverse('dashboard:project_canvas_position', args=[self.project.slug, 0])
        self.client.force_login(self.member)
        response = self.client.post(url, data=json.dumps({'x': 12.5, 'y': 87}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.canvas_x, 12.5)
        self.assertEqual(self.project.canvas_y, 87)

        response = self.client.post(url, data=json.dumps({'x': 999, 'y': -40}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.canvas_x, 92)
        self.assertEqual(self.project.canvas_y, 10)

        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(url, data=json.dumps({'x': 5, 'y': 5}), content_type='application/json').status_code, 404)


class TaskCloseReopenGuardTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user('mgr', 'mgr@example.com', 'password', role=Role.PROFESSOR)
        self.member = User.objects.create_user('member', 'member@example.com', 'password', role=Role.RESEARCHER)
        self.project = Project.objects.create(title='Guard study', description='A study', created_by=self.manager)
        ProjectMembership.objects.create(project=self.project, user=self.manager, role=MemberRole.OWNER)
        ProjectMembership.objects.create(project=self.project, user=self.member, role=MemberRole.MEMBER)
        self.task = Task.objects.create(project=self.project, title='Survey', assigned_to=self.member)

    def test_completed_task_cannot_be_reopened_by_approve_checkmark(self):
        self.task.status = TaskStatus.DONE
        self.task.save(update_fields=['status'])
        self.client.force_login(self.manager)
        response = self.client.post(reverse('dashboard:project_toggle_task', args=[self.project.slug, self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DONE)

    def test_completed_task_toggle_posts_are_ignored(self):
        self.task.status = TaskStatus.DONE
        self.task.save(update_fields=['status'])
        self.client.force_login(self.manager)
        for _ in range(3):
            self.client.post(reverse('dashboard:project_toggle_task', args=[self.project.slug, self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DONE)

    def test_toggle_task_requires_post(self):
        self.client.force_login(self.manager)
        url = reverse('dashboard:project_toggle_task', args=[self.project.slug, self.task.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.TODO)

    def test_open_task_can_still_be_marked_done_by_manager(self):
        self.client.force_login(self.manager)
        self.client.post(reverse('dashboard:project_toggle_task', args=[self.project.slug, self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DONE)

    def test_reopen_task_route_reopens_completed_task(self):
        self.task.status = TaskStatus.DONE
        self.task.save(update_fields=['status'])
        self.client.force_login(self.manager)
        response = self.client.post(reverse('dashboard:project_reopen_task', args=[self.project.slug, self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.TODO)
        self.assertEqual(response.status_code, 302)

    def test_reopen_task_clears_approval_badge(self):
        self.task.status = TaskStatus.DONE
        self.task.review_status = ReviewStatus.APPROVED
        self.task.save(update_fields=['status', 'review_status'])
        self.client.force_login(self.manager)
        self.client.post(reverse('dashboard:project_reopen_task', args=[self.project.slug, self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.TODO)
        self.assertEqual(self.task.review_status, ReviewStatus.NONE)

    def test_reopen_task_only_for_completed_tasks(self):
        self.client.force_login(self.manager)
        self.client.post(reverse('dashboard:project_reopen_task', args=[self.project.slug, self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.TODO)

    def test_reopen_task_requires_manager(self):
        self.task.status = TaskStatus.DONE
        self.task.save(update_fields=['status'])
        self.client.force_login(self.member)
        response = self.client.post(reverse('dashboard:project_reopen_task', args=[self.project.slug, self.task.pk]))
        self.assertEqual(response.status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DONE)

    def test_reopen_task_requires_post(self):
        self.task.status = TaskStatus.DONE
        self.task.save(update_fields=['status'])
        self.client.force_login(self.manager)
        url = reverse('dashboard:project_reopen_task', args=[self.project.slug, self.task.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DONE)


class SandyProjectDraftTests(TestCase):
    def setUp(self):
        self.guarantor = User.objects.create_user(
            'prof', 'prof@example.com', 'password', role=Role.PROFESSOR,
            first_name='Ada', last_name='Lovelace',
        )
        self.invitee = User.objects.create_user(
            'invitee', 'invitee@example.com', 'password', role=Role.RESEARCHER,
            first_name='Grace', last_name='Hopper',
        )
        self.draft_url = reverse('dashboard:sandy_project_draft')
        self.create_url = reverse('dashboard:project_create')

    def _post_draft(self, payload):
        return self.client.post(
            self.draft_url,
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_researcher_cannot_store_a_project_draft(self):
        researcher = User.objects.create_user(
            'res', 'res@example.com', 'password', role=Role.RESEARCHER,
        )
        self.client.force_login(researcher)
        response = self._post_draft({'answers': {'title': 'Blocked'}})
        self.assertEqual(response.status_code, 403)

    def test_empty_draft_is_rejected(self):
        self.client.force_login(self.guarantor)
        response = self._post_draft({'answers': {'title': '  ', 'invites': 'skip'}})
        self.assertEqual(response.status_code, 400)

    def test_draft_prefills_create_form_and_resolves_invites(self):
        self.client.force_login(self.guarantor)
        response = self._post_draft({
            'answers': {
                'title': 'Climate sensors',
                'description': 'A field study of urban sensors.',
                'objectives': '',
                'application_question': 'What field experience do you have?',
                'funding_status': 'partial',
                'start_date': '2026-09-01',
                'invites': 'invitee, missing-user',
            },
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['redirect'], self.create_url)
        self.assertIn('title', response.json()['fields'])
        self.assertIn('initial_members', response.json()['fields'])

        create_page = self.client.get(self.create_url)
        self.assertEqual(create_page.status_code, 200)
        self.assertContains(create_page, 'Sandy filled in what you already shared')
        self.assertContains(create_page, 'Climate sensors')
        self.assertContains(create_page, 'A field study of urban sensors.')
        self.assertContains(create_page, 'What field experience do you have?')
        self.assertContains(
            create_page,
            f'name="initial_members" value="{self.invitee.pk}"',
            html=False,
        )
        self.assertContains(
            create_page,
            f'value="{self.invitee.pk}" checked',
            html=False,
        )

    def test_skipped_invites_leave_members_empty(self):
        self.client.force_login(self.guarantor)
        response = self._post_draft({
            'answers': {
                'title': 'Solo draft',
                'description': 'No invites yet.',
            },
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('initial_members', response.json()['fields'])
        create_page = self.client.get(self.create_url)
        self.assertContains(create_page, 'Solo draft')
        self.assertNotContains(
            create_page,
            f'name="initial_members" value="{self.invitee.pk}" checked',
            html=False,
        )


class TaskNavigationGapTests(TestCase):
    """Assigned tasks must offer both View and Submit from the project task list."""

    def setUp(self):
        self.manager = User.objects.create_user('navmgr', 'navmgr@example.com', 'password', role=Role.PROFESSOR)
        self.member = User.objects.create_user('navmember', 'navmember@example.com', 'password', role=Role.RESEARCHER)
        self.other_member = User.objects.create_user('navother', 'navother@example.com', 'password', role=Role.RESEARCHER)
        self.project = Project.objects.create(title='Nav study', description='A study', created_by=self.manager)
        ProjectMembership.objects.create(project=self.project, user=self.manager, role=MemberRole.OWNER)
        ProjectMembership.objects.create(project=self.project, user=self.member, role=MemberRole.MEMBER)
        ProjectMembership.objects.create(project=self.project, user=self.other_member, role=MemberRole.MEMBER)
        self.task = Task.objects.create(project=self.project, title='Write the survey', assigned_to=self.member)

    def _detail_url(self):
        return reverse('dashboard:project_task_detail', args=[self.project.slug, self.task.pk])

    def _list_page(self):
        return self.client.get(reverse('dashboard:project_detail', args=[self.project.slug]))

    def test_assignee_sees_view_alongside_submit_for_pending_task(self):
        self.client.force_login(self.member)
        response = self._list_page()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{self._detail_url()}"', count=2)
        self.assertContains(response, 'Submit →')

    def test_assignee_sees_single_view_after_submitting(self):
        self.task.review_status = ReviewStatus.SUBMITTED
        self.task.save(update_fields=['review_status'])
        self.client.force_login(self.member)
        response = self._list_page()
        self.assertContains(response, f'href="{self._detail_url()}"', count=1)
        self.assertContains(response, 'View →')
        self.assertNotContains(response, 'Submit →')

    def test_manager_sees_edit_without_submit_link(self):
        self.client.force_login(self.manager)
        response = self._list_page()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{self._detail_url()}"', count=1)
        self.assertContains(response, 'Edit →')
        self.assertNotContains(response, 'Submit →')

    def test_fellow_member_sees_no_action_link_on_assigned_task(self):
        self.client.force_login(self.other_member)
        response = self._list_page()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'href="{self._detail_url()}"')


class InvitationMembershipTests(TestCase):
    """Invitation-based membership: nothing becomes real until the invitee accepts."""

    def setUp(self):
        self.manager = User.objects.create_user('invmg', 'invmg@example.com', 'password', role=Role.PROFESSOR)
        self.invitee = User.objects.create_user('invitee2', 'invitee2@example.com', 'password', role=Role.RESEARCHER)
        self.other = User.objects.create_user('invother', 'invother@example.com', 'password', role=Role.RESEARCHER)
        self.admin = User.objects.create_user('invadmin', 'invadmin@example.com', 'password', role=Role.ADMIN)
        self.project = Project.objects.create(title='Inv study', description='A study', created_by=self.manager)
        ProjectMembership.objects.create(project=self.project, user=self.manager, role=MemberRole.OWNER)
        self.detail_url = reverse('dashboard:project_detail', args=[self.project.slug])

    def _invite(self, inviter=None, invitee=None, role='member', message=''):
        user = invitee or self.invitee
        self.client.force_login(inviter or self.manager)
        return self.client.post(
            reverse('dashboard:project_invite_member', args=[self.project.slug]),
            {'user': user.pk, 'role': role, 'message': message},
        )

    def _canvas_node_ids(self):
        response = self.client.get(reverse('dashboard:project_canvas_data', args=[self.project.slug]))
        self.assertEqual(response.status_code, 200)
        return {str(member['id']) for member in response.json()['members']}

    def test_invite_creates_pending_invitation_without_membership_or_chat(self):
        response = self._invite(message='Join our team!')
        self.assertRedirects(response, self.detail_url)
        invitation = ProjectInvitation.objects.get(project=self.project, invitee=self.invitee)
        self.assertEqual(invitation.status, InvitationStatus.PENDING)
        self.assertEqual(invitation.role, MemberRole.MEMBER)
        self.assertEqual(invitation.message, 'Join our team!')
        self.assertEqual(invitation.invited_by, self.manager)
        self.assertFalse(ProjectMembership.objects.filter(project=self.project, user=self.invitee).exists())
        self.assertTrue(self.invitee.notifications.filter(notif_type='project_invitation').exists())
        conversation = get_or_create_project_chat(self.project)
        self.assertNotIn(self.invitee, conversation.participants.all())

    def test_invitee_has_no_canvas_bubble_until_accepted(self):
        self._invite()
        self.client.force_login(self.manager)
        self.assertNotIn(str(self.invitee.pk), self._canvas_node_ids())

    def test_duplicate_pending_invitation_is_blocked(self):
        self._invite()
        self._invite()
        self.assertEqual(
            ProjectInvitation.objects.filter(project=self.project, invitee=self.invitee).count(), 1,
        )

    def test_accept_creates_membership_chat_bubble_and_manager_notice(self):
        self._invite(role='manager')
        invitation = ProjectInvitation.objects.get(project=self.project, invitee=self.invitee)
        self.client.force_login(self.invitee)
        response = self.client.post(
            reverse('dashboard:respond_to_invitation', args=[invitation.pk]), {'action': 'accept'},
        )
        self.assertRedirects(response, reverse('dashboard:home'))
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, InvitationStatus.ACCEPTED)
        self.assertIsNotNone(invitation.responded_at)
        membership = ProjectMembership.objects.get(project=self.project, user=self.invitee)
        self.assertEqual(membership.role, MemberRole.MANAGER)
        conversation = get_or_create_project_chat(self.project)
        self.assertIn(self.invitee, conversation.participants.all())
        self.assertTrue(self.manager.notifications.filter(notif_type='project_joined').exists())
        self.client.force_login(self.manager)
        self.assertIn(str(self.invitee.pk), self._canvas_node_ids())

    def test_decline_creates_no_membership_and_notifies_sender(self):
        self._invite()
        invitation = ProjectInvitation.objects.get(project=self.project, invitee=self.invitee)
        self.client.force_login(self.invitee)
        response = self.client.post(
            reverse('dashboard:respond_to_invitation', args=[invitation.pk]), {'action': 'decline'},
        )
        self.assertRedirects(response, reverse('dashboard:home'))
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, InvitationStatus.DECLINED)
        self.assertFalse(ProjectMembership.objects.filter(project=self.project, user=self.invitee).exists())
        self.assertTrue(self.manager.notifications.filter(notif_type='project_invitation_declined').exists())

    def test_only_the_invitee_can_respond(self):
        self._invite()
        invitation = ProjectInvitation.objects.get(project=self.project, invitee=self.invitee)
        self.client.force_login(self.other)
        response = self.client.post(
            reverse('dashboard:respond_to_invitation', args=[invitation.pk]), {'action': 'accept'},
        )
        self.assertEqual(response.status_code, 404)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, InvitationStatus.PENDING)

    def test_responded_invitation_cannot_be_answered_again(self):
        self._invite()
        invitation = ProjectInvitation.objects.get(project=self.project, invitee=self.invitee)
        self.client.force_login(self.invitee)
        self.client.post(reverse('dashboard:respond_to_invitation', args=[invitation.pk]), {'action': 'accept'})
        response = self.client.post(reverse('dashboard:respond_to_invitation', args=[invitation.pk]), {'action': 'accept'})
        self.assertEqual(response.status_code, 404)

    def test_reinvite_allowed_after_decline(self):
        self._invite()
        invitation = ProjectInvitation.objects.get(project=self.project, invitee=self.invitee)
        self.client.force_login(self.invitee)
        self.client.post(reverse('dashboard:respond_to_invitation', args=[invitation.pk]), {'action': 'decline'})
        self._invite()
        self.assertEqual(
            ProjectInvitation.objects.filter(project=self.project, invitee=self.invitee, status=InvitationStatus.PENDING).count(),
            1,
        )

    def test_manager_can_cancel_pending_invitation(self):
        self._invite()
        invitation = ProjectInvitation.objects.get(project=self.project, invitee=self.invitee)
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('dashboard:project_cancel_invitation', args=[self.project.slug, invitation.pk]),
        )
        self.assertRedirects(response, self.detail_url)
        self.assertFalse(ProjectInvitation.objects.filter(pk=invitation.pk).exists())

    def test_non_manager_cannot_invite_or_cancel(self):
        ProjectMembership.objects.create(project=self.project, user=self.other, role=MemberRole.MEMBER)
        self._invite(inviter=self.other)
        self.assertEqual(ProjectInvitation.objects.filter(project=self.project).count(), 0)
        self._invite()
        invitation = ProjectInvitation.objects.get(project=self.project, invitee=self.invitee)
        self.client.force_login(self.other)
        response = self.client.post(
            reverse('dashboard:project_cancel_invitation', args=[self.project.slug, invitation.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_direct_add_is_admin_only(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('dashboard:project_direct_add_member', args=[self.project.slug]),
            {'user': self.invitee.pk, 'role': 'member'},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProjectMembership.objects.filter(project=self.project, user=self.invitee).exists())

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('dashboard:project_direct_add_member', args=[self.project.slug]),
            {'user': self.invitee.pk, 'role': 'member'},
        )
        self.assertRedirects(response, self.detail_url)
        self.assertTrue(ProjectMembership.objects.filter(project=self.project, user=self.invitee).exists())


class CanvasInviteFlowTests(TestCase):
    """Right-click canvas invite: type-to-search + the same KAN-40 invitation
    endpoint — no membership or canvas bubble until the invitee accepts."""

    def setUp(self):
        self.manager = User.objects.create_user('canvmg', 'canvmg@example.com', 'password', role=Role.PROFESSOR)
        self.member = User.objects.create_user('canvmb', 'canvmb@example.com', 'password', role=Role.RESEARCHER)
        self.invitee = User.objects.create_user('canvite', 'canvite@example.com', 'password', role=Role.RESEARCHER)
        self.target = User.objects.create_user('canvtgt', 'canvtgt@example.com', 'password', role=Role.RESEARCHER,
                                               first_name='Alexandra', last_name='Carter')
        self.student = User.objects.create_user('canvstu', 'canvstu@example.com', 'password', role=Role.STUDENT)
        self.project = Project.objects.create(title='Canvas invite study', description='A study',
                                              created_by=self.manager)
        ProjectMembership.objects.create(project=self.project, user=self.manager, role=MemberRole.OWNER)
        self.member_membership = ProjectMembership.objects.create(
            project=self.project, user=self.member, role=MemberRole.MEMBER,
        )
        self.search_url = reverse('dashboard:project_search_invitable_users', args=[self.project.slug])
        self.invite_url = reverse('dashboard:project_invite_member', args=[self.project.slug])

    def _json_invite(self, user, role='member'):
        return self.client.post(
            self.invite_url,
            data=json.dumps({'user': user.pk, 'role': role}),
            content_type='application/json',
        )

    def _canvas_project_flags(self):
        response = self.client.get(reverse('dashboard:project_canvas_data', args=[self.project.slug]))
        self.assertEqual(response.status_code, 200)
        return response.json()['project']

    def _canvas_node_ids(self):
        response = self.client.get(reverse('dashboard:project_canvas_data', args=[self.project.slug]))
        self.assertEqual(response.status_code, 200)
        return {str(member['id']) for member in response.json()['members']}

    def test_search_requires_manager(self):
        self.client.force_login(self.member)
        response = self.client.get(self.search_url, {'q': 'can'})
        self.assertEqual(response.status_code, 404)
        self.client.logout()
        response = self.client.get(self.search_url, {'q': 'can'})
        self.assertEqual(response.status_code, 302)

    def test_search_returns_nothing_below_two_characters(self):
        self.client.force_login(self.manager)
        response = self.client.get(self.search_url, {'q': 'c'})
        self.assertEqual(response.json(), {'users': []})
        response = self.client.get(self.search_url, {})
        self.assertEqual(response.json(), {'users': []})

    def test_search_matches_name_and_username(self):
        self.client.force_login(self.manager)
        by_name = self.client.get(self.search_url, {'q': 'alexandra'}).json()['users']
        self.assertEqual([u['username'] for u in by_name], ['canvtgt'])
        by_username = self.client.get(self.search_url, {'q': 'canvite'}).json()['users']
        self.assertEqual([u['username'] for u in by_username], ['canvite'])

    def test_search_excludes_members_and_pending_invitees(self):
        self.client.force_login(self.manager)
        self._json_invite(self.invitee)
        usernames = {u['username'] for u in self.client.get(self.search_url, {'q': 'canv'}).json()['users']}
        self.assertEqual(usernames, {'canvtgt'})

    def test_search_only_lists_invitable_roles(self):
        self.client.force_login(self.manager)
        usernames = {u['username'] for u in self.client.get(self.search_url, {'q': 'canv'}).json()['users']}
        self.assertNotIn('canvstu', usernames)

    def test_json_invite_uses_same_endpoint_and_creates_pending_invitation(self):
        self.client.force_login(self.manager)
        response = self._json_invite(self.target, role='manager')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        invitation = ProjectInvitation.objects.get(project=self.project, invitee=self.target)
        self.assertEqual(invitation.status, InvitationStatus.PENDING)
        self.assertEqual(invitation.role, MemberRole.MANAGER)
        self.assertTrue(self.target.notifications.filter(notif_type='project_invitation').exists())
        self.assertFalse(ProjectMembership.objects.filter(project=self.project, user=self.target).exists())
        self.assertNotIn(str(self.target.pk), self._canvas_node_ids())

    def test_json_invite_reports_duplicate_pending_without_creating_another(self):
        self.client.force_login(self.manager)
        self._json_invite(self.target)
        response = self._json_invite(self.target)
        self.assertFalse(response.json()['ok'])
        self.assertEqual(
            ProjectInvitation.objects.filter(project=self.project, invitee=self.target, status=InvitationStatus.PENDING).count(),
            1,
        )

    def test_json_invite_requires_manager(self):
        self.client.force_login(self.member)
        response = self._json_invite(self.target)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProjectInvitation.objects.filter(project=self.project, invitee=self.target).exists())

    def test_form_invite_still_redirects_with_messages(self):
        self.client.force_login(self.manager)
        response = self.client.post(self.invite_url, {'user': self.target.pk, 'role': 'member'})
        self.assertRedirects(response, reverse('dashboard:project_detail', args=[self.project.slug]))
        self.assertTrue(ProjectInvitation.objects.filter(project=self.project, invitee=self.target).exists())

    def test_payload_flags_for_invite_openness_and_permission(self):
        self.client.force_login(self.manager)
        flags = self._canvas_project_flags()
        self.assertTrue(flags['can_invite'])
        self.assertTrue(flags['is_open_for_members'])

        self.project.status = ProjectStatus.CLOSED
        self.project.save(update_fields=['status'])
        flags = self._canvas_project_flags()
        self.assertFalse(flags['is_open_for_members'])

        self.client.force_login(self.member)
        flags = self._canvas_project_flags()
        self.assertFalse(flags['can_invite'])