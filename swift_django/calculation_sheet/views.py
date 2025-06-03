import json
from django.shortcuts import render, redirect
from django.forms import  inlineformset_factory
from django.db import connections
from django.http import JsonResponse

from .forms import CalculationSheetForm, CalculationSheetRowDebitForm, CalculationSheetRowCreditForm
from .models import CalculationSheet, CalculationSheetRow

# Create your views here.

def home(request):    
    """ Домашняя страница """
    
    calc_sheets = CalculationSheet.objects.all()
    return render(request, 'calculation_sheet/calculation_sheet_list.html', {'calc_sheets': calc_sheets})
  
def create_calculation_sheet(request):
    """ Создаем расчетный лист """
    
    # Formset
    CalculationSheetRowDebitFormSet = inlineformset_factory(parent_model=CalculationSheet, model=CalculationSheetRow, 
        form=CalculationSheetRowDebitForm, extra=1)    
    CalculationSheetRowCreditFormSet = inlineformset_factory(parent_model=CalculationSheet, model=CalculationSheetRow, 
        form=CalculationSheetRowCreditForm, extra=1)
    print(request.method)
    if request.method == 'POST':        
        calc_sheet_form = CalculationSheetForm(request.POST)
        #debit_row_formset = CalculationSheetRowDebitFormSet(request.POST)
        #credit_row_formset = CalculationSheetRowCreditFormSet(request.POST)
        if calc_sheet_form.is_valid():
            calc_sheet_instance = calc_sheet_form.save(commit=False)
            calc_sheet_instance.author = request.user
            debit_row_formset = CalculationSheetRowDebitFormSet(request.POST, instance=calc_sheet_instance, prefix='debit')
            credit_row_formset = CalculationSheetRowCreditFormSet(request.POST, instance=calc_sheet_instance, prefix='credit')

            if debit_row_formset.is_valid() and credit_row_formset.is_valid(): 
                calc_sheet_instance.save()
                              
                debit_row_formset_instance = debit_row_formset.save(commit=False)              
                for debit_row_form_instance in debit_row_formset_instance:
                    debit_row_form_instance.author = request.user
                    debit_row_form_instance.save()            
            
                credit_row_formset_instance = credit_row_formset.save(commit=False)
                for credit_row_form_instance in credit_row_formset_instance:
                    credit_row_form_instance.author = request.user
                    credit_row_form_instance.save()                               
                            
                return redirect('calculation_sheet:home')
    else:
        debit_row_formset = CalculationSheetRowDebitFormSet(prefix='debit')
        credit_row_formset = CalculationSheetRowCreditFormSet(prefix='credit')
        calc_sheet_form = CalculationSheetForm()   
        clients_data = []
        with connections['sol_cargo'].cursor() as cursor:
            sql = '''
                    select job_num from sol_cargo.airflow_swift_rus_profit 
                    where created_time >= '2024-01-01' and profit_approval_status != 'согласовано'
                    order by created_time desc;
                '''
            cursor.execute(sql)
            rows = cursor.fetchall()
            orders_data = [row[0] for row in rows]  
            sql = ''' select customer_name, ifnull(tax_registration_number, '') from airflow_customer_info order by customer_name; '''
            cursor.execute(sql)
            rows = cursor.fetchall()
            for customer, inn in rows:
                clients_data.append({'customer': customer, 'inn': inn})
            
            sql = ''' select service_acticle from airflow_service_acticle; '''
            cursor.execute(sql)
            rows = cursor.fetchall()
            article_services_data = [row[0] for row in rows]
        context = {
            'calc_sheet_form': calc_sheet_form,
            'debit_row_formset': debit_row_formset,
            'credit_row_formset': credit_row_formset,
            'orders_data': json.dumps(orders_data),
            'clients_data': json.dumps(clients_data),
            'article_services_data': json.dumps(article_services_data),
        }
        return render(request, 'calculation_sheet/create_calculation_sheet.html', context)
    
def fetch_order_data_from_db(job_num):
    job_num_data = {}
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
            result = cursor.fetchone()
        job_num_data = {"department": result[0],
                    "box": result[1],
                    "client": result[2],
                    "station_from": result[3],
                    "station_to": result[4]}
    return job_num_data

    
def fetch_data_for_order(request):
    job_num = request.POST.get('job_num', None)
    return_data = fetch_order_data_from_db(job_num)
    return JsonResponse(return_data)

def view_info(request, id):
    calc_sheet_info = CalculationSheet.objects.get(id=id)
    calc_sheet_debit_rows = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Доход')    
    calc_sheet_credit_rows = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Расход')    
    debit_total_sum, credit_total_sum = 0, 0
    
    for calc_sheet_debit_row in calc_sheet_debit_rows:
        calc_sheet_debit_row.total = round((calc_sheet_debit_row.calc_row_ttl_price_without_nds + calc_sheet_debit_row.calc_row_ttl_nds_price) * calc_sheet_debit_row.calc_row_exchange_rate, 2)
        debit_total_sum += calc_sheet_debit_row.total   
             
    for calc_sheet_credit_row in calc_sheet_credit_rows:
        calc_sheet_credit_row.total = round((calc_sheet_credit_row.calc_row_ttl_price_without_nds + calc_sheet_credit_row.calc_row_ttl_nds_price) * calc_sheet_credit_row.calc_row_exchange_rate, 2)
        credit_total_sum += calc_sheet_credit_row.total
        
    job_num_data = fetch_order_data_from_db(calc_sheet_info.order_no)
    context = {
        'calc_sheet_info': calc_sheet_info,
        'order_department': job_num_data['department'],
        'order_box': job_num_data['box'],
        'order_client': job_num_data['client'],
        'order_station_from': job_num_data['station_from'],
        'order_station_to': job_num_data['station_to'],
        'debit_total_sum': round(debit_total_sum, 2),
        'credit_total_sum': round(credit_total_sum, 2),
        'margin_total_sum': round(debit_total_sum - credit_total_sum, 2),
        'margin_prcnt': f'{round((debit_total_sum - credit_total_sum) / debit_total_sum * 100, 2)} %',
        'calc_sheet_debit_rows': calc_sheet_debit_rows,
        'calc_sheet_credit_rows': calc_sheet_credit_rows
    }
    
    return render(request, 'calculation_sheet/calculation_sheet_info.html', context)
    