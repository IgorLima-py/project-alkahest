from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views # <--- IMPORTANTE PARA O LOGIN

# Importando TODAS as views que criamos
from vault.views import (
    library_view, 
    game_detail_view, 
    profile_view, 
    add_game_view,
    my_lists_view, 
    create_list_view, 
    list_detail_view, 
    add_to_list_view,
    export_data_view,       # Exportação JSON
    edit_review_view,       # Editar Review
    delete_review_view,     # Deletar Review
    edit_library_entry_view,# Editar Jogo na Biblioteca
    edit_tip_view,          # Editar Dica
    delete_tip_view         # Deletar Dica
)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # ==========================================
    # ROTAS DE AUTENTICAÇÃO (O QUE ESTAVA FALTANDO)
    # ==========================================
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # ==========================================
    # ROTAS PRINCIPAIS
    # ==========================================
    path('', library_view, name='library'),
    path('game/<uuid:game_id>/', game_detail_view, name='game_detail'),
    path('profile/', profile_view, name='profile'),
    path('add/', add_game_view, name='add_game'),
    path('export/', export_data_view, name='export_data'),
    
    # ==========================================
    # ROTAS DE LISTAS
    # ==========================================
    path('lists/', my_lists_view, name='my_lists'),
    path('lists/create/', create_list_view, name='create_list'),
    path('lists/<uuid:list_id>/', list_detail_view, name='list_detail'),
    path('lists/add/<uuid:game_id>/', add_to_list_view, name='add_to_list'),

    # ==========================================
    # ROTAS DE EDIÇÃO E DELEÇÃO (CRUDs)
    # ==========================================
    # Reviews
    path('review/edit/<uuid:review_id>/', edit_review_view, name='edit_review'),
    path('review/delete/<uuid:review_id>/', delete_review_view, name='delete_review'),
    
    # Biblioteca
    path('library/entry/edit/<uuid:entry_id>/', edit_library_entry_view, name='edit_library_entry'),
    
    # Dicas
    path('tip/edit/<uuid:tip_id>/', edit_tip_view, name='edit_tip'),
    path('tip/delete/<uuid:tip_id>/', delete_tip_view, name='delete_tip'),
]