from django.conf import settings

def analytics_settings(request):
    """
    Injeta variáveis de Analytics em todos os templates.
    Blindagem: Se não tiver configurado, retorna strings vazias para não quebrar o JS.
    """
    return {
        'ENABLE_ANALYTICS': getattr(settings, 'ENABLE_ANALYTICS', False),
        'POSTHOG_API_KEY': getattr(settings, 'POSTHOG_API_KEY', ''),
        'POSTHOG_HOST': getattr(settings, 'POSTHOG_HOST', 'https://app.posthog.com'),
    }
