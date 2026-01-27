from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from vault import views # Importar o módulo inteiro evita linhas gigantes de imports

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Auth
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Core
    path('', views.library_view, name='library'),
    path('game/<uuid:game_id>/', views.game_detail_view, name='game_detail'),
    path('profile/', views.profile_view, name='profile'),
    path('add/', views.add_game_view, name='add_game'),
    path('export/', views.export_data_view, name='export_data'),
    
    # Edição (CRUD)
    path('library/entry/edit/<uuid:entry_id>/', views.edit_library_entry_view, name='edit_library_entry'),
    path('review/edit/<uuid:review_id>/', views.edit_review_view, name='edit_review'),
    path('review/delete/<uuid:review_id>/', views.delete_review_view, name='delete_review'),
    path('tip/edit/<uuid:tip_id>/', views.edit_tip_view, name='edit_tip'),
    path('tip/delete/<uuid:tip_id>/', views.delete_tip_view, name='delete_tip'),
    
    # Listas
    path('lists/', views.my_lists_view, name='my_lists'),
    path('lists/create/', views.create_list_view, name='create_list'),
    path('lists/<uuid:list_id>/', views.list_detail_view, name='list_detail'),
    path('lists/add/<uuid:game_id>/', views.add_to_list_view, name='add_to_list'),
]