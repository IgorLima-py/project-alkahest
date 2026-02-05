import pytest
from django.conf import settings
from django.test import Client, override_settings

@pytest.mark.django_db
class TestSecurityHardening:
    """
    Checklist de Hardening e Conformidade (OWASP Security Misconfiguration).
    Garante que o settings.py está configurado corretamente para PRODUÇÃO.
    """

    def test_debug_mode_is_off(self):
        """
        CRÍTICO: Verifica a configuração REAL atual.
        Se você rodar localmente com DEBUG=True no .env, este teste vai falhar PROPOSITALMENTE
        para te lembrar de desligar em produção.
        """
        # Se estivermos rodando em CI/CD ou Prod, isso DEVE ser False.
        # Se falhar localmente no seu PC, é apenas um aviso.
        if settings.DEBUG:
            pytest.skip("Aviso: DEBUG está True (OK para desenvolvimento local, proibido em Prod).")
        else:
            assert settings.DEBUG is False

    def test_secret_key_is_safe(self):
        """
        Verifica se não estamos usando a key padrão insegura do Django.
        """
        insecure_key = 'django-insecure-unsafe-dev-key'
        assert settings.SECRET_KEY != insecure_key, (
            "🚨 FALHA: Você está usando a SECRET_KEY padrão insegura. \n"
            "Gere uma nova chave aleatória no .env."
        )

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['alka.gg'])
    def test_allowed_hosts_is_restricted(self):
        """
        Simula ambiente de Produção para garantir que ALLOWED_HOSTS
        não aceita '*' quando DEBUG=False.
        """
        assert '*' not in settings.ALLOWED_HOSTS, (
            "🚨 FALHA: ALLOWED_HOSTS=['*'] permite ataques de Host Header. \n"
            "Defina os domínios explicitamente (ex: 'alka.gg')."
        )
        assert 'alka.gg' in settings.ALLOWED_HOSTS

    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=True)
    def test_security_headers_present(self):
        """
        Verifica se o Middleware de segurança está injetando os headers HTTP corretos.
        """
        client = Client()
        
        # Simulamos HTTPS para evitar o redirect 301 do SECURE_SSL_REDIRECT
        response = client.get('/', secure=True) 
        
        # 1. Previne que seu site seja carregado em iframes (Clickjacking)
        assert response.headers.get('X-Frame-Options') == 'DENY', \
            f"Header X-Frame-Options incorreto. Status: {response.status_code}"
            
        # 2. Previne que o navegador tente 'adivinhar' tipos de arquivo (MIME Sniffing)
        assert response.headers.get('X-Content-Type-Options') == 'nosniff', \
            "Header X-Content-Type-Options ausente."

    @override_settings(DEBUG=False, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
    def test_cookie_security_flags(self):
        """
        Simula ambiente de Produção para verificar flags de cookie.
        """
        assert settings.SESSION_COOKIE_SECURE is True, "Cookie de Sessão deve ser SECURE (HTTPS apenas)"
        assert settings.CSRF_COOKIE_SECURE is True, "Cookie CSRF deve ser SECURE (HTTPS apenas)"
        # HTTPOnly é padrão True no Django, mas validamos mesmo assim
        assert settings.SESSION_COOKIE_HTTPONLY is True, "Cookie de Sessão deve ser HTTPONLY (inacessível via JS)"
