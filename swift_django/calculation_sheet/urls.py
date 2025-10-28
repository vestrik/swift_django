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
    path('<int:id>/download_pdf/', views.download_pdf, name='download_pdf'),
    path('<int:calc_sheet_id>/sol_upload_calc_sheet_to_sol/', views.sol_upload_calc_sheet_to_sol, name='sol_upload_calc_sheet_to_sol'),
    
]