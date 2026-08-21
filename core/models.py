from django.db import models


class LandingFeature(models.Model):
    """A feature/pillar displayed on the landing page."""

    title = models.CharField(max_length=120)
    body = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    icon = models.CharField(
        max_length=40,
        blank=True,
        help_text="Fallback icon name (e.g. 'book', 'users', 'calendar', 'lifebuoy'). Used if no image is provided.",
    )

    image_url = models.URLField(
        blank=True,
        help_text="Optional external image URL. Used if no image is uploaded.",
    )
    image = models.ImageField(
        upload_to="landing_features/",
        blank=True,
        null=True,
        help_text="Upload an image from your computer. Takes priority over image_url.",
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Landing feature"
        verbose_name_plural = "Landing features"

    def __str__(self):
        return self.title

    def get_image_source(self):
        """Return the best available image source: uploaded image > image_url > None."""
        if self.image:
            return self.image.url
        if self.image_url:
            return self.image_url
        return None

    def get_icon_svg(self):
        """Return SVG markup for the fallback icon."""
        icons = {
            "book": '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.9" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 19.5V6a2 2 0 012-2h8l4 4v11.5a.5.5 0 01-.5.5h-13a.5.5 0 01-.5-.5z"/><path stroke-linecap="round" d="M14 4v4h4M8 13h8M8 16h5"/></svg>',
            "users": '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.9" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9 9 0 100-18 9 9 0 000 18zM3.6 9h16.8M3.6 15h16.8M12 3a15 15 0 010 18a15 15 0 000-18z"/></svg>',
            "calendar": '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.9" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>',
            "lifebuoy": '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.9" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9 9 0 100-18 9 9 0 000 18zM12 9a3 3 0 100-6 3 3 0 000 6z"/></svg>',
        }
        return icons.get(self.icon, icons["book"])