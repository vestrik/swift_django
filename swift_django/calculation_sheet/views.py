import json
from django.shortcuts import render, redirect
from django.forms import  inlineformset_factory
from django.db import connections
from django.http import JsonResponse

from .forms import CalculationSheetForm, CalculationSheetRowForm
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
        form=CalculationSheetRowForm, extra=3)
    
    if request.method == 'POST':        
        calc_sheet_form = CalculationSheetForm(request.POST)
        row_formset = CalculationSheetRowFormSet(request.POST)
        if calc_sheet_form.is_valid():
            calc_sheet_instance = calc_sheet_form.save(commit=False)
            calc_sheet_instance.author = request.user
            row_formset = CalculationSheetRowFormSet(request.POST, instance=calc_sheet_instance)
            if row_formset.is_valid():
                row_formset_instance = row_formset.save(commit=False)
                for row_form_instance in row_formset_instance:
                    row_form_instance.author = request.user                
                calc_sheet_instance.save()
                row_formset_instance.save()
                return redirect('calculation_sheet:home')
    else:
        row_formset = CalculationSheetRowFormSet()
        calc_sheet_form = CalculationSheetForm()   
        with connections['sol_cargo'].cursor() as cursor:
            sql = '''
                    select job_num from sol_cargo.airflow_swift_rus_profit 
                    where created_time >= '2024-01-01' and profit_approval_status != 'согласовано'
                    order by created_time desc;
                '''
            cursor.execute(sql)
            rows = cursor.fetchall()
        data = [row[0] for row in rows]  
        return render(request, 'calculation_sheet/create_calculation_sheet.html', {'calc_sheet_form': calc_sheet_form, 'row_formset': row_formset, 'data': json.dumps(data) })
    
def fetch_data_for_order(request):
    job_num = request.POST.get('job_num', None)
    
    if job_num is not None:
        sql = f'''
            select 
                department, 
                trim(both ' & 0x' from trim(both '0x & ' from concat(ifnull(box_amount_40, ''), 'x', ifnull(box_type_40, ''), ' & ', ifnull(box_amount_20, ''), 'x', ifnull(box_type_20, '')))) as box, 
                entrust_customer_name, departure_station_name, aim_station_name 
            from sol_cargo.airflow_swift_rus_profit 
            where job_num = '{job_num}';
        '''
        with connections['sol_cargo'].cursor() as cursor:
            cursor.execute(sql)
            job_num_data = cursor.fetchone()
        
        return_data = {"department": job_num_data[0],
                            "box": job_num_data[1],
                            "client": job_num_data[2],
                            "station_from": job_num_data[3],
                            "station_to": job_num_data[4]}
    else: 
        return_data = {}
    return JsonResponse(return_data)