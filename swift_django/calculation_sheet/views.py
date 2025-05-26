from django.shortcuts import render, redirect

from .forms import CalculationSheetRowForm
from .models import CalculationSheet

# Create your views here.

def home(request):    
    calc_sheets = CalculationSheet.objects.all()
    return render(request, 'calculation_sheet/calculation_sheet_list.html', {'calc_sheets': calc_sheets})
    
def create_calculation_sheet(request):
    if request.method == 'POST':
        form = CalculationSheetRowForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.author = request.user
            instance.save()
            return redirect('calculation_sheet:home')
    else:
        form = CalculationSheetRowForm()                
        return render(request, 'calculation_sheet/create_calculation_sheet.html', {'form': form})