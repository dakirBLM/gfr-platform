from django.contrib import admin

from .models import LandingFeature


@admin.register(LandingFeature)
class LandingFeatureAdmin(admin.ModelAdmin):
    list_display = ("title", "order", "is_active", "has_image", "icon")
    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title", "body")
    ordering = ("order", "id")

    fieldsets = (
        (None, {
            "fields": ("title", "body", "order", "is_active"),
        }),
        ("Visual", {
            "fields": ("icon", "image", "image_url"),
            "description": "Upload an image (priority) or provide an external image URL. If neither is set, the icon is used as fallback.",
        }),
    )

    def has_image(self, obj):
        return bool(obj.image or obj.image_url)
    has_image.boolean = True
    has_image.short_description = "Has image"