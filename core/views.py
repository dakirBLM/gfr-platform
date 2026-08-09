from django.shortcuts import render
from django.views.generic import TemplateView


class HomeView(TemplateView):
    template_name = 'core/home.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['stats'] = {
            'researchers': 12480,
            'institutions': 312,
            'journals': 24,
            'projects': 187,
        }
        ctx['pillars'] = [
            {
                'title': 'Peer-reviewed publishing',
                'body': 'Double-blind review, transparent editorial workflows, and international ethical standards.',
                'icon': 'book',
            },
            {
                'title': 'Research collaboration',
                'body': 'Form teams, manage tasks, and connect with scholars across disciplines and borders.',
                'icon': 'users',
            },
            {
                'title': 'Conferences & workshops',
                'body': 'International events, abstract submissions, and academic summer programs.',
                'icon': 'calendar',
            },
            {
                'title': 'Funding & support',
                'body': 'Discover grants, sponsorships, and exemption mechanisms for under-funded researchers.',
                'icon': 'lifebuoy',
            },
        ]
        return ctx


class AboutView(TemplateView):
    template_name = 'core/about.html'
