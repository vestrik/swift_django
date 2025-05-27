from django.shortcuts import render, redirect
from django.forms import  inlineformset_factory

from .forms import CalculationSheetForm
from .models import CalculationSheet, CalculationSheetRow

# Create your views here.

def home(request):    
    """ Домашняя страница """
    
    calc_sheets = CalculationSheet.objects.all()
    return render(request, 'calculation_sheet/calculation_sheet_list.html', {'calc_sheets': calc_sheets})
  
def create_calculation_sheet(request):
    """ Создаем расчетный лист """
    
    # Formset
    CalculationSheetRowFormSet = inlineformset_factory(parent_model=CalculationSheet, model=CalculationSheetRow, 
        fields='__all__', extra=3)
    
    if request.method == 'POST':        
        calc_sheet_form = CalculationSheetForm(request.POST)
        row_formset = CalculationSheetRowFormSet(request.POST)
        if calc_sheet_form.is_valid():
            instance = calc_sheet_form.save()
            row_formset = CalculationSheetRowFormSet(request.POST, instance=instance)
            if row_formset.is_valid():
                row_formset.save()
                return redirect('calculation_sheet:home')
    else:
        row_formset = CalculationSheetRowFormSet()
        calc_sheet_form = CalculationSheetForm()        
        return render(request, 'calculation_sheet/create_calculation_sheet.html', {'calc_sheet_form': calc_sheet_form, 'row_formset': row_formset})
    