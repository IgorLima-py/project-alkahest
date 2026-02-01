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


@register.simple_tag
def get_rating_color(rating_value_0_to_100):
    """
    Recebe int 0-100 (do banco) e retorna a cor HEX baseada na regra:
    0-3.9 (0-39): Vermelho (#ff1744)
    4-6.9 (40-69): Amarelo (#ffd600)
    7-8.9 (70-89): Verde (#00e676)
    9-10 (90-100): Roxo (#940ef9)
    """
    if rating_value_0_to_100 is None:
        return "#6c757d" # Cinza (Sem nota)
        
    try:
        val = int(rating_value_0_to_100)
        # Comparando na escala 0-100 direto pra evitar float math
        if val < 40: return "#ff1744"
        if val < 70: return "#ffd600"
        if val < 90: return "#00e676"
        return "#940ef9"
    except (ValueError, TypeError):
        return "#6c757d"

@register.filter
def to_display_rating(rating_value_0_to_100):
    """
    Converte 0-100 (banco) para string formatada '9.5' (display).
    Remove decimais se for zero (9.0 -> 9).
    """
    if rating_value_0_to_100 is None:
        return "-"
    try:
        val = float(rating_value_0_to_100) / 10.0
        # Formata com 1 casa decimal e remove .0 se existir
        return f"{val:.1f}".rstrip('0').rstrip('.') if val % 1 != 0 else f"{int(val)}"
    except:
        return "-"

@register.filter
def is_dark_bg(rating_value_0_to_100):
    """Retorna True se a cor de fundo for escura (Vermelho/Roxo), para virar texto branco."""
    if rating_value_0_to_100 is None: return True # Cinza é escuro
    try:
        val = int(rating_value_0_to_100)
        # Vermelho (<40) e Roxo (>=90) precisam de texto branco
        return val < 40 or val >= 90
    except:
        return False