import pytest
from django.conf import settings
from django.test import Client

@pytest.mark.django_db
class TestSecurityHardening:
    """
    Checklist de Hardening e Conformidade (OWASP Security Misconfiguration).
    Garante que o settings.py está configurado para PRODUÇÃO.
    """

    def test_debug_mode_is_off(self):
        """
        CRÍTICO: DEBUG deve ser False em produção para não vazar stack traces e variáveis de ambiente.
        """
        assert settings.DEBUG is False, (
            "🚨 FALHA DE SEGURANÇA: DEBUG = True. \n"
            "Altere no seu .env ou settings.py para False imediatamente."
        )

    def test_secret_key_is_safe(self):
        """
        Verifica se não estamos usando a key padrão insegura do Django.
        """
        insecure_key = 'django-insecure-unsafe-dev-key'
        assert settings.SECRET_KEY != insecure_key, (
            "🚨 FALHA: Você está usando a SECRET_KEY padrão insegura. \n"
            "Gere uma nova chave aleatória no .env."
        )

    def test_allowed_hosts_is_restricted(self):
        """
        Previne Host Header Injection. Não pode ser '*'.
        """
        # Nota: Se você estiver rodando local, talvez precise ajustar isso,
        # mas em produção '*' é proibido.
        assert '*' not in settings.ALLOWED_HOSTS, (
            "🚨 FALHA: ALLOWED_HOSTS=['*'] permite ataques de Host Header. \n"
            "Defina os domínios explicitamente (ex: 'meusite.com')."
        )

    def test_security_headers_present(self):
        """
        Verifica se o Middleware de segurança está injetando os headers HTTP corretos.
        """
        client = Client()
        
        # --- A MUDANÇA É AQUI (secure=True) ---
        # Simulamos HTTPS para evitar o redirect 301
        response = client.get('/', secure=True) 
        # --------------------------------------
        
        # 1. Previne que seu site seja carregado em iframes (Clickjacking)
        assert response.headers.get('X-Frame-Options') == 'DENY', \
            f"Header X-Frame-Options incorreto. Status: {response.status_code}"
            
        # 2. Previne que o navegador tente 'adivinhar' tipos de arquivo (MIME Sniffing)
        assert response.headers.get('X-Content-Type-Options') == 'nosniff', \
            "Header X-Content-Type-Options ausente."

    def test_cookie_security_flags(self):
        """
        Verifica se os cookies de sessão estão marcados como seguros.
        """
        # Só exigimos isso se não estiver em DEBUG (Prod)
        if not settings.DEBUG:
            assert settings.SESSION_COOKIE_SECURE is True, "Cookie de Sessão deve ser SECURE (HTTPS apenas)"
            assert settings.CSRF_COOKIE_SECURE is True, "Cookie CSRF deve ser SECURE (HTTPS apenas)"
            assert settings.SESSION_COOKIE_HTTPONLY is True, "Cookie de Sessão deve ser HTTPONLY (inacessível via JS)"
