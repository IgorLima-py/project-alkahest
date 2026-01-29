from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.contrib.auth.models import User
from .models import UserFollow, Notification, NotificationType

# 1. Notificar quando alguém começa a seguir (SOCIAL_FOLLOW)
@receiver(post_save, sender=UserFollow)
def notify_new_follower(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            recipient=instance.target,
            notification_type=NotificationType.SOCIAL_FOLLOW,
            title="Novo Seguidor!",
            message=f"{instance.follower.username} começou a te seguir.",
            # Link para o perfil de quem seguiu (ajuste a rota se seu perfil usar username na URL)
            link_url=reverse('profile') 
        )

# 2. Notificar Boas-Vindas ao criar conta (SYSTEM)
@receiver(post_save, sender=User)
def notify_welcome(sender, instance, created, **kwargs):
    if created: # Só na criação, não em updates
        Notification.objects.create(
            recipient=instance,
            notification_type=NotificationType.SYSTEM,
            title="Bem-vindo ao Alkahest!",
            message="Configure sua biblioteca importando jogos da Steam ou adicionando manualmente.",
            link_url=reverse('add_game')
        )
