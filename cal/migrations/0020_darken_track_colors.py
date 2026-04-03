"""Darken track colors from -600 to -700 for WCAG AA contrast with white text."""

from django.db import migrations

# Old -600 → new -700 mapping (only the 9 colors that failed 4.5:1)
COLOR_MAP = {
    '#ea580c': '#c2410c',  # orange
    '#d97706': '#b45309',  # amber
    '#ca8a04': '#a16207',  # yellow
    '#65a30d': '#4d7c0f',  # lime
    '#16a34a': '#15803d',  # green
    '#059669': '#047857',  # emerald
    '#0d9488': '#0f766e',  # teal
    '#0891b2': '#0e7490',  # cyan
    '#0284c7': '#0369a1',  # sky
}


def darken_colors(apps, schema_editor):
    Asset = apps.get_model('cal', 'Asset')
    for old, new in COLOR_MAP.items():
        Asset.objects.filter(color=old).update(color=new)


def lighten_colors(apps, schema_editor):
    Asset = apps.get_model('cal', 'Asset')
    for old, new in COLOR_MAP.items():
        Asset.objects.filter(color=new).update(color=old)


class Migration(migrations.Migration):

    dependencies = [
        ('cal', '0019_remove_event_actual_end_remove_event_actual_start_and_more'),
    ]

    operations = [
        migrations.RunPython(darken_colors, lighten_colors),
    ]
