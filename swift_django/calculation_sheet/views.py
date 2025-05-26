from django.shortcuts import render

# Create your views here.

def home(request):
    
    return render(request, 'calculation_sheet/create_calculation_sheet.html')