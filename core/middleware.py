from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

class BetaAccessMiddleware:
    """
    Bloqueia acesso a todo o site exceto para usuários que inseriram 
    um código Beta válido na sessão.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        # Rotas permitidas mesmo sem beta
        self.whitelist = [
            '/beta-login', # SEM BARRA NO FINAL
            '/admin',
            '/static',
            '/media',
            '/accounts',
            '/health',
        ]


    def __call__(self, request):
        # 1. Se Beta estiver desligado, deixa passar tudo
        if not getattr(settings, 'BETA_ACTIVE', True):
            return self.get_response(request)

        # 2. Verifica Whitelist
        path = request.path
        if any(path.startswith(allowed) for allowed in self.whitelist):
            return self.get_response(request)

        # 3. Verifica se tem o cookie/sessão de Beta
        # NOTA: Usamos a sessão para persistir o acesso sem precisar logar no Django User ainda
        has_beta_access = request.session.get('has_beta_access', False)

        if not has_beta_access:
            return redirect('beta_login')

        return self.get_response(request)
