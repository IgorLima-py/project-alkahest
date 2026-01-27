from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def render_stars(value):
    """
    Recebe um float (ex: 3.5) e retorna HTML de estrelas.
    Ex: 3.5 -> ★★★½☆
    """
    if value is None:
        value = 0
    
    full_stars = int(value)
    half_star = 1 if (value - full_stars) >= 0.5 else 0
    empty_stars = 5 - full_stars - half_star
    
    html = '<span class="text-warning" style="font-size: 1rem;">'
    html += '<i class="bi bi-star-fill"></i>' * full_stars
    html += '<i class="bi bi-star-half"></i>' * half_star
    html += '<i class="bi bi-star"></i>' * empty_stars
    html += '</span>'
    
    return mark_safe(html)