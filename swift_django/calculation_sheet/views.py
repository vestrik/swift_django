import logging
import json
import base64
import traceback
from weasyprint import HTML, CSS
from django.utils import timezone
from django.contrib import messages
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.forms import  inlineformset_factory, modelformset_factory
from django.db import connections
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from decimal import InvalidOperation
from django.core.exceptions import ObjectDoesNotExist

from .filters import CalculationSheetFilter
from .forms import CalculationSheetForm, CalculationSheetRowDebitForm, CalculationSheetRowCreditForm
from .models import CalculationSheet, CalculationSheetRow
from .sbis_worker import SbisWorker

logger = logging.getLogger(__name__)

ERR_MESSAGE_ENDING = ' Обратитесь на почту m.golovanov@uk-swift.ru.'

def fetch_orders_from_db():
    """ Получаем список заявок из БД """
    
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
    """ Получаем из БД клиентов, их ИНН, а также статьи услуг """
    
    clients_data = []
    with connections['sol_cargo'].cursor() as cursor:
        sql = ''' select customer_name, ifnull(tax_registration_number, '') from airflow_customer_info order by customer_name; '''
        cursor.execute(sql)
        rows = cursor.fetchall()
        for customer, inn in rows:
            clients_data.append({'customer': customer, 'inn': inn})
        sql = ''' select service_acticle from airflow_service_article; '''
        cursor.execute(sql)
        rows = cursor.fetchall()
        article_services_data = [row[0] for row in rows]
    return clients_data, article_services_data

def fetch_order_data_from_db(job_num):
    """ По номеру заявки получаем ее данные из БД """
    
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

@login_required(login_url='accounts:login')
def home(request):    
    """ Домашняя страница """
    
    calc_sheets = CalculationSheet.objects.all().order_by('-created_at')
    calc_sheet_filter = CalculationSheetFilter(request.GET, queryset=calc_sheets)
    calc_sheets = calc_sheet_filter.qs[:10]
    context = {
        'calc_sheets': calc_sheets,
        'calc_sheet_filter': calc_sheet_filter,
        'redirect_to': request.path
    }
    return render(request, 'calculation_sheet/calculation_sheet_list.html', context)

def process_rows_formset(request, formset, calc_sheet_id=None, need_deletion=False):
    """ Сохраняем созданный/измененный формсет. При необходимости удаляем записи в БД. """
    
    formset_instance = formset.save(commit=False)    

    for row_form_instance in formset_instance:      
        if row_form_instance.created_by == '':
            row_form_instance.created_by = str(request.user)         
        row_form_instance.edited_by = str(request.user)
        row_form_instance.edited_at = timezone.now()
        if calc_sheet_id is not None:
            row_form_instance.calculation_sheet_id = calc_sheet_id
        row_form_instance.save()
    if need_deletion:
        for form_to_delete in formset.deleted_objects:
            form_to_delete.delete()     

@login_required(login_url='accounts:login')
def create_calculation_sheet(request):
    """ Создаем расчетный лист """
    
    err_text = f"Ошибка при создании расчетного листа.{ERR_MESSAGE_ENDING}"
    
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
                process_rows_formset(request, debit_row_formset)
                process_rows_formset(request, credit_row_formset)
            else:
                messages.add_message(request, messages.ERROR, err_text)
        else:
            print(calc_sheet_form.errors)
            if 'Расчетный лист с таким Order no уже существует' in str(calc_sheet_form.errors):
                err_text = f"Расчетный лист для заявки {str(calc_sheet_form['order_no'].value())} уже существует.{ERR_MESSAGE_ENDING}"
            messages.add_message(request, messages.ERROR, err_text)
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
    """ AJAX-ом получаем данные заявки и отдаем для рендера """
    
    job_num = request.POST.get('job_num', None)
    return_data = fetch_order_data_from_db(job_num)
    return JsonResponse(return_data)

def check_if_calc_sheet_exists(request):
    """ Проверяем, существует ли расчетный лист по заявке """
    
    job_num = request.POST.get('job_num', None)
    try:
        CalculationSheet.objects.get(order_no=job_num)
        return_data = {'already_exists': 'true'}
    except ObjectDoesNotExist:
        return_data = {'already_exists': 'false'}
    
    return JsonResponse(return_data)

def calc_ttl_sum_for_calc_sheet_rows(calc_sheet_rows):    
    """ Вычисляем общую сумму в таблице по заявке """
    
    total_sum = 0
    for calc_sheet_row in calc_sheet_rows:
        calc_sheet_row.total = round((calc_sheet_row.calc_row_ttl_price_without_nds + calc_sheet_row.calc_row_ttl_nds_price) * calc_sheet_row.calc_row_exchange_rate, 2)
        total_sum += calc_sheet_row.total 
    return total_sum

def calc_margin_for_calc_sheet(debit_total_sum, credit_total_sum):   
    """ Вычисляем маржу и ее % по заявке """
     
    margin = round(debit_total_sum - credit_total_sum, 2)
    try:
        margin_prcnt = f'{round((debit_total_sum - credit_total_sum) / debit_total_sum * 100, 2)} %'
    except (ZeroDivisionError, InvalidOperation):
        margin_prcnt = 0    
    
    return margin, margin_prcnt

@login_required(login_url='accounts:login')
def view_info(request, id):
    """ Просмотр расчетного листа """
    
    calc_sheet_info = CalculationSheet.objects.get(id=id)
    calc_sheet_debit_rows = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Доход')    
    calc_sheet_credit_rows = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Расход')    
    debit_total_sum, credit_total_sum = calc_ttl_sum_for_calc_sheet_rows(calc_sheet_debit_rows), calc_ttl_sum_for_calc_sheet_rows(calc_sheet_credit_rows)
        
    job_num_data = fetch_order_data_from_db(calc_sheet_info.order_no)
    margin, margin_prcnt = calc_margin_for_calc_sheet(debit_total_sum, credit_total_sum)
    context = {
        'calc_sheet_info': calc_sheet_info,
        'order_department': job_num_data['department'],
        'order_box': job_num_data['box'],
        'order_client': job_num_data['client'],
        'order_station_from': job_num_data['station_from'],
        'order_station_to': job_num_data['station_to'],
        'debit_total_sum': round(debit_total_sum, 2),
        'credit_total_sum': round(credit_total_sum, 2),
        'margin_total_sum': margin,
        'margin_prcnt': margin_prcnt,
        'calc_sheet_debit_rows': calc_sheet_debit_rows,
        'calc_sheet_credit_rows': calc_sheet_credit_rows
    }
    
    return render(request, 'calculation_sheet/calculation_sheet_info.html', context)    

@login_required(login_url='accounts:login')
def edit_info(request, id):    
    """ Изменение расчетного листа """
    
    CalculationSheetRowDebitFormSet = modelformset_factory(model=CalculationSheetRow, form=CalculationSheetRowDebitForm, extra=0, can_delete=True)    
    CalculationSheetRowCreditFormSet = modelformset_factory(model=CalculationSheetRow, form=CalculationSheetRowCreditForm, extra=0, can_delete=True)   
    if request.method == 'POST':
        debit_row_formset = CalculationSheetRowDebitFormSet(request.POST, prefix='debit')
        credit_row_formset = CalculationSheetRowCreditFormSet(request.POST, prefix='credit')
        if debit_row_formset.is_valid() and credit_row_formset.is_valid():             
            if debit_row_formset.has_changed():
                process_rows_formset(request, debit_row_formset, calc_sheet_id=id, need_deletion=True)                          
            if credit_row_formset.has_changed():
                process_rows_formset(request, credit_row_formset, calc_sheet_id=id, need_deletion=True)                            
                        
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
    
def make_pdf(calc_sheet_info, order_data, debit_total_sum, credit_total_sum, margin, margin_prcnt, debit_data, credit_data):
    """ Создаем ПДФ """

    context = {
        'calc_sheet_info': calc_sheet_info,
        'order_department': order_data['department'],
        'order_box': order_data['box'],
        'order_client': order_data['client'],
        'order_station_from': order_data['station_from'],
        'order_station_to': order_data['station_to'],
        'debit_total_sum': round(debit_total_sum, 2),
        'credit_total_sum': round(credit_total_sum, 2),
        'margin_total_sum': margin,
        'margin_prcnt': margin_prcnt,
        'calc_sheet_debit_rows': debit_data,
        'calc_sheet_credit_rows': credit_data
    }
    # Рендерим html шаблон с данными
    html = render_to_string("calculation_sheet/templates_for_pdf_render/calculation_sheet_for_sbis.html", context)    
    # Читаем css 
    with open('assets/css/pdf_styles.css') as file:
        css_str = file.read()        
    # Формируем ПДФ, сохраняем в память
    byte_ = HTML(string=html).write_pdf(presentational_hints=True, stylesheets=[CSS(string=css_str)])
    # Переводим в base64
    bs = base64.b64encode(byte_).decode('ascii')              
    return bs

@login_required(login_url='accounts:login')
def sbis_create_task(request, id):
    """ Создаем задачу в Сбисе """
    
    try:
        # Получаем данные расчетного листа
        calc_sheet_info = CalculationSheet.objects.get(id=id)
        order_data = fetch_order_data_from_db(calc_sheet_info.order_no)
        debit_data = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Доход')
        credit_data = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Расход')
        debit_total_sum, credit_total_sum = calc_ttl_sum_for_calc_sheet_rows(debit_data), calc_ttl_sum_for_calc_sheet_rows(credit_data)
        margin, margin_prcnt = calc_margin_for_calc_sheet(debit_total_sum, credit_total_sum)
    
        pdf = make_pdf(calc_sheet_info, order_data, debit_total_sum, credit_total_sum, margin, margin_prcnt, debit_data, credit_data)   
               
        sbis_href, sbis_doc_id = SbisWorker(request.user).create_approval_for_calc_list(calc_sheet_info.order_no, calc_sheet_info.calc_sheet_no, pdf)

        calc_sheet_info.sbis_href = sbis_href
        calc_sheet_info.sbis_doc_id = sbis_doc_id
        calc_sheet_info.sbis_approval_status = 'cоздана задача в Сбис (черновик)'
        calc_sheet_info.save()
        
    except Exception as e:
        logger.error(''.join(traceback.format_exception(type(e), value=e, tb=e.__traceback__, chain=False, limit=4)))
        messages.add_message(request, messages.ERROR, f"Не удалось создать задачу в Сбис.{ERR_MESSAGE_ENDING}")
    return redirect('calculation_sheet:view_info', calc_sheet_info.id)