import json
from django.utils import timezone
from django.shortcuts import render, redirect
from django.forms import  inlineformset_factory, modelformset_factory
from django.db import connections
from django.http import JsonResponse

from .forms import CalculationSheetForm, CalculationSheetRowDebitForm, CalculationSheetRowCreditForm
from .models import CalculationSheet, CalculationSheetRow


def fetch_orders_from_db():
    with connections['sol_cargo'].cursor() as cursor:
        sql = '''
                select job_num from sol_cargo.airflow_swift_rus_profit 
                where created_time >= '2024-01-01' and profit_approval_status != 'согласовано'
                order by created_time desc;
            '''
        cursor.execute(sql)
        rows = cursor.fetchall()
        orders = [row[0] for row in rows]  
    return orders

def fetch_clients_and_services_data_from_db():
    clients_data = []
    with connections['sol_cargo'].cursor() as cursor:
        sql = ''' select customer_name, ifnull(tax_registration_number, '') from airflow_customer_info order by customer_name; '''
        cursor.execute(sql)
        rows = cursor.fetchall()
        for customer, inn in rows:
            clients_data.append({'customer': customer, 'inn': inn})
        sql = ''' select service_acticle from airflow_service_acticle; '''
        cursor.execute(sql)
        rows = cursor.fetchall()
        article_services_data = [row[0] for row in rows]
    return clients_data, article_services_data

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
    if request.method == 'POST':        
        calc_sheet_form = CalculationSheetForm(request.POST)
        if calc_sheet_form.is_valid():
            calc_sheet_instance = calc_sheet_form.save(commit=False)
            calc_sheet_instance.author = str(request.user)
            debit_row_formset = CalculationSheetRowDebitFormSet(request.POST, instance=calc_sheet_instance, prefix='debit')
            credit_row_formset = CalculationSheetRowCreditFormSet(request.POST, instance=calc_sheet_instance, prefix='credit')

            if debit_row_formset.is_valid() and credit_row_formset.is_valid(): 
                calc_sheet_instance.save()
                              
                debit_row_formset_instance = debit_row_formset.save(commit=False)              
                for debit_row_form_instance in debit_row_formset_instance:
                    debit_row_form_instance.created_by = str(request.user)
                    debit_row_form_instance.edited_by = str(request.user)
                    debit_row_form_instance.save()            
            
                credit_row_formset_instance = credit_row_formset.save(commit=False)
                for credit_row_form_instance in credit_row_formset_instance:
                    
                    credit_row_form_instance.created_by = str(request.user)
                    credit_row_form_instance.edited_by = str(request.user)
                    credit_row_form_instance.save()                               
                            
                return redirect('calculation_sheet:home')
    else:
        debit_row_formset = CalculationSheetRowDebitFormSet(prefix='debit')
        credit_row_formset = CalculationSheetRowCreditFormSet(prefix='credit')
        calc_sheet_form = CalculationSheetForm()   
        orders = fetch_orders_from_db()
        clients_data, article_services_data = fetch_clients_and_services_data_from_db()

        context = {
            'calc_sheet_form': calc_sheet_form,
            'debit_row_formset': debit_row_formset,
            'credit_row_formset': credit_row_formset,
            'orders': json.dumps(orders),
            'clients_data': json.dumps(clients_data),
            'article_services_data': json.dumps(article_services_data),
        }
        return render(request, 'calculation_sheet/create_calculation_sheet.html', context)
    
    
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
    try:
        margin_prcnt = f'{round((debit_total_sum - credit_total_sum) / debit_total_sum * 100, 2)} %'
    except ZeroDivisionError:
        margin_prcnt = 'Деление на 0!'
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
        'margin_prcnt': margin_prcnt,
        'calc_sheet_debit_rows': calc_sheet_debit_rows,
        'calc_sheet_credit_rows': calc_sheet_credit_rows
    }
    
    return render(request, 'calculation_sheet/calculation_sheet_info.html', context)

def process_rows_formset(request, formset, calc_sheet_id):
    """ Обрабатываем изменение формсета: удаляем отмеченные, прописываем дату изменения, пользователя """
    formset_instance = formset.save(commit=False)    

    for row_form_instance in formset_instance:      
        if row_form_instance.created_by == '':
            row_form_instance.created_by = str(request.user)         
        row_form_instance.edited_by = str(request.user)
        row_form_instance.edited_at = timezone.now()
        row_form_instance.calculation_sheet_id = calc_sheet_id
        row_form_instance.save()
    for form_to_delete in formset.deleted_objects:
        form_to_delete.delete()       

def edit_info(request, id):    
    CalculationSheetRowDebitFormSet = modelformset_factory(model=CalculationSheetRow, form=CalculationSheetRowDebitForm, extra=0, can_delete=True)    
    CalculationSheetRowCreditFormSet = modelformset_factory(model=CalculationSheetRow, form=CalculationSheetRowCreditForm, extra=0, can_delete=True)   
    if request.method == 'POST':
        debit_row_formset = CalculationSheetRowDebitFormSet(request.POST, prefix='debit')
        credit_row_formset = CalculationSheetRowCreditFormSet(request.POST, prefix='credit')
        if debit_row_formset.is_valid() and credit_row_formset.is_valid():             
            if debit_row_formset.has_changed():
                process_rows_formset(request, debit_row_formset, id)                          
            if credit_row_formset.has_changed():
                process_rows_formset(request, credit_row_formset, id)                             
                        
            return redirect('calculation_sheet:view_info', id)
    else:
        calc_sheet_info = CalculationSheet.objects.get(id=id)
        debit_data = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Доход')
        credit_data = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Расход')
        debit_row_formset = CalculationSheetRowDebitFormSet(prefix='debit', queryset=debit_data)
        credit_row_formset = CalculationSheetRowCreditFormSet(prefix='credit', queryset=credit_data)        
        order_data = fetch_order_data_from_db(calc_sheet_info.order_no)

        clients_data, article_services_data = fetch_clients_and_services_data_from_db()
        context = {
            'calc_sheet_info': calc_sheet_info,
            'order_data': order_data,
            'debit_row_formset': debit_row_formset,
            'credit_row_formset': credit_row_formset,
            'clients_data': json.dumps(clients_data),
            'article_services_data': json.dumps(article_services_data),
        }   
        return render(request, 'calculation_sheet/calculation_sheet_edit.html', context)