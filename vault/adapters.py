from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_field
from django.contrib import messages
from django.shortcuts import redirect
import uuid
import logging

logger = logging.getLogger(__name__)

class AlkahestSocialAdapter(DefaultSocialAccountAdapter):
    def authentication_error(self, request, provider_id, error=None, exception=None, extra_context=None):
        """
        Captura erros catastróficos durante o OAuth (Ex: Steam fora do ar).
        Evita a tela amarela de Debug (500).
        """
        logger.error(
            f"Steam OAuth Failure. Provider: {provider_id}. Error: {error}. Exception: {exception}"
        )
        
        msg = "Não foi possível conectar aos servidores da Steam no momento. Tente novamente em alguns minutos ou use o login manual."
        
        # Feedback visual para o usuário
        if request:
            messages.error(request, msg)
            
        # Redireciona para login em vez de explodir erro
        return redirect('login')

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        
        # Lógica de Username Seguro (Mantida do seu original)
        username = data.get('username') or data.get('name') or ''
        if not username or not username.isalnum():
            safe_id = uuid.uuid4().hex[:8]
            user_field(user, 'username', f"steam_{safe_id}")
        else:
            user_field(user, 'username', username)
            
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        from .models import UserProfile
        UserProfile.objects.get_or_create(user=user)
        return user
