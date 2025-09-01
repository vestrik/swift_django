from django.urls import path
from . import views

app_name='calculation_sheet'

urlpatterns = [
    path('', views.home, name='home'),
    path('create', views.create_calculation_sheet, name='create'),
    path('fetch_data_for_order', views.fetch_data_for_order, name='fetch_data_for_order'),
    path('check_if_calc_sheet_exists', views.check_if_calc_sheet_exists, name='check_if_calc_sheet_exists'),
    path('<int:id>', views.view_info, name='view_info'),
    path('<int:id>/edit/', views.edit_info, name='edit'),
    path('<int:id>/sbis_create_task/', views.sbis_create_task, name='sbis_create_task'),
    path('<int:id>/sol_add_calc_sheet/', views.sol_add_calc_sheet, name='sol_add_calc_sheet'),
]