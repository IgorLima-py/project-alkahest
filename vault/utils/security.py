import nh3
import markdown
from functools import wraps
from django_ratelimit.decorators import ratelimit
from django.conf import settings

def sanitize_html(content):
    """
    Sanitiza strings contendo Markdown/HTML.
    Uso: Em views antes de salvar GameTips, Listas ou Reviews.
    """
    if not content:
        return ""
    
    # Primeiro converte Markdown para HTML
    html = markdown.markdown(content)
    
    # 🛡️ FIX: Removido 'rel' dos atributos de 'a' porque o nh3 (ammonia) tem um bug
    # onde você não pode customizar 'rel' manualmente. A lib adiciona automaticamente.
    # Whitelist estrita (Seguindo padrão do Models)
    allowed_tags = {'b', 'i', 'strong', 'em', 'p', 'br', 'ul', 'ol', 'li', 'a', 'blockquote', 'code', 'h1', 'h2', 'hr'}
    allowed_attrs = {
        'a': {'href', 'title'}, # ❌ REMOVIDO 'target' e 'rel' (causam panic no nh3)
        'img': {'src', 'alt'}   # ❌ REMOVIDO 'class' (não é crítico para segurança)
    }
    
    # Limpa tags maliciosas (<script>, <iframe>, onclick, etc)
    # O nh3 adiciona automaticamente rel="noopener noreferrer" em links externos
    clean_html = nh3.clean(html, tags=allowed_tags, attributes=allowed_attrs)
    return clean_html

def friendly_ratelimit(key='ip', rate='5/m', block=True, method='ALL'):
    """
    Wrapper para o django_ratelimit.
    Regra: Se o usuário for STAFF ou SUPERUSER, ignora o limite.
    """
    def decorator(fn):
        @wraps(fn)
        def _wrapped(request, *args, **kwargs):
            # 🔓 Pass Livre para Admins e Staff
            if request.user.is_authenticated and request.user.is_staff:
                return fn(request, *args, **kwargs)
            
            # Aplica o Rate Limit padrão para mortais
            limiter = ratelimit(key=key, rate=rate, block=block, method=method)
            return limiter(fn)(request, *args, **kwargs)
            
        return _wrapped
    return decorator
