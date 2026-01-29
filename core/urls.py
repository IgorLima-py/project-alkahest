from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django_ratelimit.decorators import ratelimit # <--- Necessário pip install django-ratelimit
from vault import views

urlpatterns = [
    # ==========================================
    # ADMIN & AUTH
    # ==========================================
    path('admin/', admin.site.urls),
    
    # Allauth (Steam, Social Login)
    path('accounts/', include('allauth.urls')), 

    # Login Customizado com Rate Limit (10 tentativas por hora por IP)
    # Protege contra Bruteforce Attack
    path('login/', ratelimit(key='ip', rate='10/h', block=True)(
        auth_views.LoginView.as_view(template_name='login.html')
    ), name='login'),

    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # ==========================================
    # CORE DASHBOARD
    # ==========================================
    path('', views.dashboard_view, name='dashboard'), 
    
    # ==========================================
    # BIBLIOTECA & JOGOS
    # ==========================================
    path('library/', views.library_view, name='library'),
    path('add/', views.add_game_view, name='add_game'), # "add" vem antes de IDs dinâmicos por segurança
    
    # Detalhe do Jogo (UUID)
    path('game/<uuid:game_id>/', views.game_detail_view, name='game_detail'),
    
    # Edição de Entrada na Biblioteca
    path('library/entry/edit/<uuid:entry_id>/', views.edit_library_entry_view, name='edit_library_entry'),

    # ==========================================
    # PERFIL & CONFIGURAÇÕES (LGPD)
    # ==========================================
    path('profile/', views.profile_view, name='profile'),
    
    # Configurações de Dados (LGPD) - Rotas Novas
    path('settings/export/', views.request_export_view, name='request_export'), # Dispara a task de exportar
    path('settings/delete/', views.delete_account_view, name='delete_account'), # Soft delete da conta

    # ==========================================
    # REVIEWS & TIPS (CRUD)
    # ==========================================
    path('review/edit/<uuid:review_id>/', views.edit_review_view, name='edit_review'),
    path('review/delete/<uuid:review_id>/', views.delete_review_view, name='delete_review'),
    
    path('tip/edit/<uuid:tip_id>/', views.edit_tip_view, name='edit_tip'),
    path('tip/delete/<uuid:tip_id>/', views.delete_tip_view, name='delete_tip'),

    # ==========================================
    # LISTAS (USER LISTS)
    # ==========================================
    # Ordem: Específicas (create) antes das Dinâmicas (uuid)
    path('lists/', views.my_lists_view, name='my_lists'),
    path('lists/create/', views.create_list_view, name='create_list'), 
    path('lists/<uuid:list_id>/', views.list_detail_view, name='list_detail'),
    path('lists/add/<uuid:game_id>/', views.add_to_list_view, name='add_to_list'),

    # ==========================================
    # SOCIAL (FASE 4)
    # ==========================================
    path('discovery/', views.discovery_view, name='discovery'),
    path('social/', views.social_hub_view, name='social_hub'),
    path('social/rivals/', views.rivals_view, name='rivals'),
    path('social/follow/<str:username>/', views.toggle_follow_view, name='toggle_follow'),

    # ==========================================
    # API / ASYNC ACTIONS
    # ==========================================
    path('api/sync/steam/', views.trigger_steam_sync_view, name='trigger_steam_sync'),
]
