from django.urls import path
from . import views

app_name='calculation_sheet'

urlpatterns = [
    path('', views.home, name='home'),
    path('create', views.create_calculation_sheet, name='create'),
    path('fetch_data_for_order', views.fetch_data_for_order, name='fetch_data_for_order')
]