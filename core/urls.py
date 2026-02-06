from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from allauth.account.views import LoginView as AllauthLoginView # Importação da View Híbrida (Email/User)
from django_ratelimit.decorators import ratelimit
from vault import views
from vault.views import set_language_view
from vault.views_admin import merge_games_view, god_mode_dashboard

from django.contrib.auth.views import LogoutView


urlpatterns = [
    # ==========================================
    # ADMIN & CONFIG
    # ==========================================
    path('admin/', admin.site.urls),

    # --- I18N (Troca de Idioma) ---
    path('i18n/set/', set_language_view, name='set_language'),

    # ==========================================
    # AUTHENTICATION (ALLAUTH + CUSTOM)
    # ==========================================
    # Rotas padrão do Allauth (Necessário para Steam, Signup, Password Reset)
    # CRÍTICO: Isso ativa as tags {% provider_login_url %} e {% url 'account_signup' %}
    path('accounts/', include('allauth.urls')),

    # Login Customizado (Sobrescreve a rota padrão com Rate Limit e Template Dark)
    # Usamos AllauthLoginView para garantir que o formulário aceite "Username ou Email"
    path('login/', ratelimit(key='ip', rate='100/h', block=True)(
        AllauthLoginView.as_view(template_name='account/login.html')
    ), name='login'),

    # Logout (Simples)
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),

    # ==========================================
    # CORE DASHBOARD
    # ==========================================
    path('', views.dashboard_view, name='dashboard'),

    # ==========================================
    # BIBLIOTECA & JOGOS
    # ==========================================
    path('library/', views.library_view, name='library'),
    path('add/', views.add_game_view, name='add_game'), # "add" antes de IDs dinâmicos
    
    # Detalhe do Jogo (UUID)
    path('game/<uuid:game_id>/', views.game_detail_view, name='game_detail'),
    
    # Edição de Entrada na Biblioteca
    path('library/entry/edit/<uuid:entry_id>/', views.edit_library_entry_view, name='edit_library_entry'),

    # ==========================================
    # PERFIL & SETTINGS (LGPD)
    # ==========================================
    path('profile/', views.profile_view, name='profile'),
    path('settings/export/', views.request_export_view, name='request_export'), # Task Async
    path('settings/delete/', views.delete_account_view, name='delete_account'), # Soft Delete

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
    path('api/notifications/check/', views.notifications_check_view, name='notifications_check'),
    path('api/notifications/read/', views.notifications_mark_read_view, name='notifications_read'),
    path('api/sync/steam/', views.trigger_steam_sync_view, name='trigger_steam_sync'),


    # ==========================================
    # Teste Nota
    # ==========================================
    path('design/lab/', views.design_lab_view, name='design_lab'),


    # ==========================================
    # Backloggd Import
    # ==========================================
    path('settings/import/backloggd/', views.start_backloggd_import, name='start_backloggd_import'),
    path('settings/import/status/<uuid:job_id>/', views.check_import_status, name='check_import_status'),
    path('settings/import/', views.import_hub_view, name='import_hub'),
    path('settings/import/start/', views.start_backloggd_import, name='start_backloggd_import'),
    path('settings/import/status/<uuid:job_id>/', views.check_import_status, name='check_import_status'),
    path('settings/import/feed/<uuid:job_id>/', views.import_live_feed, name='import_live_feed'),

    # ==========================================
    # God Mode
    # ==========================================
    path('god/dashboard/', god_mode_dashboard, name='god_mode_dashboard'),
    path('god/merge/', merge_games_view, name='merge_games_tool'),

]
