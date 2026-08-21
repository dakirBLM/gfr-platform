from django.shortcuts import render
from django.views.generic import TemplateView

from .models import LandingFeature


class HomeView(TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["stats"] = {
            "researchers": 12480,
            "institutions": 312,
            "journals": 24,
            "projects": 187,
        }
        ctx["pillars"] = [
            {
                "title": "Peer-reviewed publishing",
                "body": "Double-blind review, transparent editorial workflows, and international ethical standards.",
                "icon": "book",
            },
            {
                "title": "Research collaboration",
                "body": "Form teams, manage tasks, and connect with scholars across disciplines and borders.",
                "icon": "users",
            },
            {
                "title": "Conferences & workshops",
                "body": "International events, abstract submissions, and academic summer programs.",
                "icon": "calendar",
            },
            {
                "title": "Funding & support",
                "body": "Discover grants, sponsorships, and exemption mechanisms for under-funded researchers.",
                "icon": "lifebuoy",
            },
        ]
        ctx["slides"] = [
            {
                "image": "img/marketing/hero-1.jpg",
                "eyebrow": "Welcome to the Global Forum for Researchers",
                "title": "Where Research<br>Finds Its<br>Community!",
            },
            {
                "image": "img/marketing/hero-2.jpg",
                "eyebrow": "Publish with confidence",
                "title": "Peer Review<br>Done Openly<br>And Fairly!",
            },
            {
                "image": "img/marketing/hero-3.jpg",
                "eyebrow": "Knowledge without borders",
                "title": "Read, Share<br>And Build<br>Together!",
            },
        ]
        ctx["highlights"] = [
            {
                "image": "img/marketing/card-journals.jpg",
                "title": "Peer-reviewed Journals",
                "meta": "24 active titles",
                "badge": "Open access",
            },
            {
                "image": "img/marketing/card-projects.jpg",
                "title": "Research Projects",
                "meta": "187 running projects",
                "badge": "Collaborate",
            },
            {
                "image": "img/marketing/card-conferences.jpg",
                "title": "Conferences & Workshops",
                "meta": "Events year-round",
                "badge": "Attend",
            },
        ]
        ctx["steps"] = [
            {
                "title": "Create Your Profile",
                "body": "Register once and keep your publications, projects, and reviews under a single academic identity.",
                "icon": "user",
            },
            {
                "title": "Submit Your Work",
                "body": "Send a manuscript to any GFR journal and follow it through double-blind review in real time.",
                "icon": "upload",
            },
            {
                "title": "Collaborate & Publish",
                "body": "Join projects, manage tasks with your team, and share results with researchers worldwide.",
                "icon": "globe",
            },
        ]
        # Landing features from database (pillars section)
        ctx["landing_features"] = LandingFeature.objects.filter(is_active=True)
        return ctx


class AboutView(TemplateView):
    template_name = "core/about.html"