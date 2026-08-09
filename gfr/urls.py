from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = 'GFR Administration'
admin.site.site_title = 'GFR Admin'
admin.site.index_title = 'Global Forum for Researchers'

urlpatterns = [
    path('', include('core.urls', namespace='core')),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('app/', include('dashboard.urls', namespace='dashboard')),
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
