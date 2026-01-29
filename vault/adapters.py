from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_field
from django.conf import settings
import uuid

class AlkahestSocialAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        """
        Garante username válido vindo da Steam.
        """
        user = super().populate_user(request, sociallogin, data)
        
        # Tenta pegar username ou name
        username = data.get('username') or data.get('name') or ''
        
        # Se for vazio ou tiver caracteres inválidos, gera um seguro
        # Steam costuma mandar nomes com espaço ou caracteres especiais que o Django odeia
        if not username or not username.isalnum():
            safe_id = uuid.uuid4().hex[:8]
            user_field(user, 'username', f"steam_{safe_id}")
        else:
            user_field(user, 'username', username)
            
        return user

    def save_user(self, request, sociallogin, form=None):
        """
        Cria UserProfile automaticamente.
        """
        user = super().save_user(request, sociallogin, form)
        
        from .models import UserProfile
        UserProfile.objects.get_or_create(user=user)
        
        return user
    
    # REMOVIDO: Métodos de validação de URL que estavam quebrando (is_safe_url)
    # Deixe o DefaultAdapter lidar com isso.
