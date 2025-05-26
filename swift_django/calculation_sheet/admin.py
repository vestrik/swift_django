from django.contrib import admin
from .models import CalculationSheet, CalculationSheetRow

# Register your models here.

admin.site.register(CalculationSheet)
admin.site.register(CalculationSheetRow)
