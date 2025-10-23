import logging
import json
import base64
import traceback
from weasyprint import HTML, CSS
from django.utils import timezone
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.forms import  inlineformset_factory, modelformset_factory
from django.db import connections
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from decimal import InvalidOperation
from django.core.exceptions import ObjectDoesNotExist

from .filters import CalculationSheetFilter
from .forms import CalculationSheetForm, CalculationSheetRowDebitForm, CalculationSheetRowCreditForm
from .models import CalculationSheet, CalculationSheetRow
from .sbis_worker import SbisWorker
from .sol_worker import SolWorker, SolIncorrectAuthDataException

logger = logging.getLogger(__name__)


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
    
    clients_data, article_services_data = [], []
    with connections['sol_cargo'].cursor() as cursor:
        sql = ''' select original_id, customer_name, ifnull(tax_registration_number, '') from airflow_customer_info order by customer_name; '''
        cursor.execute(sql)
        rows = cursor.fetchall()
        for id, customer, inn in rows:
            clients_data.append({'id': id, 'customer': customer, 'inn': inn})
        sql = ''' select original_id, service_acticle from airflow_service_article; '''
        cursor.execute(sql)
        rows = cursor.fetchall()
        for id, service_article in rows:
            article_services_data.append({'id': id, 'service_article': service_article})
    return clients_data, article_services_data

def fetch_order_data_from_db(job_num):
    """ По номеру заявки получаем ее данные из БД """
    
    job_num_data = {
        "department": "",
        "box": "",
        "client": "",
        "station_from": "",
        "station_to": ""
    }
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
        if result is not None:
            job_num_data = {
                "department": result[0],
                "box": result[1],
                "client": result[2],
                "station_from": result[3],
                "station_to": result[4]
            }
    return job_num_data

def add_names_to_rows(clients_data, article_services_data, rows):
    
    clients_data_dict = {client_data['id']:client_data['customer'] for client_data in clients_data}
    article_services_dict = {article_service['id']:article_service['service_article'] for article_service in article_services_data}    
    for row in rows:
        row.calc_row_contragent = clients_data_dict[int(row.calc_row_contragent)]
        row.calc_row_service_name = article_services_dict[int(row.calc_row_service_name)]


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
    if calc_sheet_id is not None:
        calc_sheet = CalculationSheet.objects.get(id=calc_sheet_id)
    for row_form_instance in formset_instance:
        if row_form_instance.created_by == '':
            row_form_instance.created_by = str(request.user)
        row_form_instance.edited_by = str(request.user)
        row_form_instance.edited_at = timezone.now()
        if calc_sheet_id is not None:
            row_form_instance.calculation_sheet_id = calc_sheet_id
            if calc_sheet.uploaded_at_sol == 'Да' and row_form_instance.calc_row_original_id is not None:
                row_form_instance.calc_row_need_update_in_sol = 1
        row_form_instance.save()
    if need_deletion: 
        for form_to_delete in formset.deleted_objects:
            if calc_sheet.uploaded_at_sol == 'Да':
                form_to_delete.calc_row_delete_from_sol = 1
                form_to_delete.save()
            else:
                form_to_delete.delete()
    if calc_sheet_id is not None:
        if calc_sheet.uploaded_at_sol == 'Да':
            calc_sheet.uploaded_at_sol = 'Данные не обновлены'
            calc_sheet.save()

@login_required(login_url='accounts:login')
def create_calculation_sheet(request):
    """ Создаем расчетный лист """
    
    err_text = f"Ошибка при создании расчетного листа. Обратитесь на почту m.golovanov@uk-swift.ru."
    
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
            if calc_sheet_instance.order_no == '':
                calc_sheet_instance.order_no = None
            debit_row_formset = CalculationSheetRowDebitFormSet(request.POST, instance=calc_sheet_instance, prefix='debit')
            credit_row_formset = CalculationSheetRowCreditFormSet(request.POST, instance=calc_sheet_instance, prefix='credit')

            if debit_row_formset.is_valid() and credit_row_formset.is_valid(): 
                calc_sheet_instance.save()
                process_rows_formset(request, debit_row_formset)
                process_rows_formset(request, credit_row_formset)
            else:
                
                logger.error(f"Ошибка при создании р/л для заявки {str(calc_sheet_form['order_no'].value())}: debit {debit_row_formset.errors}, credit {credit_row_formset.errors}")
                messages.add_message(request, messages.ERROR, _("Ошибка при создании р/л для заявки {order_no}").format(order_no=str(calc_sheet_form['order_no'].value())))
        else:
            if 'Расчетный лист с таким Order no уже существует' in str(calc_sheet_form.errors):
                err_text = _("Расчетный лист для заявки {order_no} уже существует. Обратитесь на почту m.golovanov@uk-swift.ru.").format(order_no=str(calc_sheet_form['order_no'].value()))
                logger.error(err_text)
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
        calc_sheet_row.total = round(calc_sheet_row.calc_row_count * calc_sheet_row.calc_row_single_amount * calc_sheet_row.calc_row_exchange_rate, 2)
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
    calc_sheet_debit_rows = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Доход', calc_row_delete_from_sol=0, calc_row_is_fixed_as_planned=0)    
    calc_sheet_credit_rows = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Расход', calc_row_delete_from_sol=0, calc_row_is_fixed_as_planned=0)    
    debit_total_sum, credit_total_sum = calc_ttl_sum_for_calc_sheet_rows(calc_sheet_debit_rows), calc_ttl_sum_for_calc_sheet_rows(calc_sheet_credit_rows)
        
    job_num_data = fetch_order_data_from_db(calc_sheet_info.order_no)
    margin, margin_prcnt = calc_margin_for_calc_sheet(debit_total_sum, credit_total_sum)
    clients_data, article_services_data = fetch_clients_and_services_data_from_db()
    add_names_to_rows(clients_data, article_services_data, calc_sheet_debit_rows)
    add_names_to_rows(clients_data, article_services_data, calc_sheet_credit_rows)
    if calc_sheet_info.order_no == None:
        calc_sheet_info.order_no = ''
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
    calc_sheet_info = CalculationSheet.objects.get(id=id)
    
    if request.method == 'POST':
        debit_row_formset = CalculationSheetRowDebitFormSet(request.POST, prefix='debit')
        credit_row_formset = CalculationSheetRowCreditFormSet(request.POST, prefix='credit')
        calc_sheet_form = CalculationSheetForm(request.POST, instance=calc_sheet_info)        
        if calc_sheet_form.is_valid():
            if calc_sheet_form.has_changed():
                calc_sheet_form_instance = calc_sheet_form.save(commit=False)
                if calc_sheet_form_instance.order_no == '':
                    calc_sheet_form_instance.order_no = None
                
            if debit_row_formset.is_valid() and credit_row_formset.is_valid():
                calc_sheet_form_instance.save()
                if debit_row_formset.has_changed():
                    process_rows_formset(request, debit_row_formset, calc_sheet_id=id, need_deletion=True)
                if credit_row_formset.has_changed():
                    process_rows_formset(request, credit_row_formset, calc_sheet_id=id, need_deletion=True)
                return redirect('calculation_sheet:view_info', id)
        else:
            print(calc_sheet_form.errors)
    else:
        debit_data = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Доход', calc_row_delete_from_sol=0, calc_row_is_fixed_as_planned=0)
        credit_data = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Расход', calc_row_delete_from_sol=0, calc_row_is_fixed_as_planned=0)

        clients_data, article_services_data = fetch_clients_and_services_data_from_db()
        debit_row_formset = CalculationSheetRowDebitFormSet(prefix='debit', queryset=debit_data)
        credit_row_formset = CalculationSheetRowCreditFormSet(prefix='credit', queryset=credit_data)
        order_data = fetch_order_data_from_db(calc_sheet_info.order_no)
        orders = fetch_orders_from_db()
        calc_sheet_form = CalculationSheetForm(instance=calc_sheet_info)
        context = {
            'calc_sheet_info': calc_sheet_info,
            'calc_sheet_form': calc_sheet_form,
            'order_data': order_data,
            'debit_row_formset': debit_row_formset,
            'credit_row_formset': credit_row_formset,
            'clients_data': json.dumps(clients_data),
            'article_services_data': json.dumps(article_services_data),
            'orders': json.dumps(orders),
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
    return bs, byte_

def download_pdf(request, id):
    try: 
        calc_sheet_info = CalculationSheet.objects.get(id=id)
        order_data = fetch_order_data_from_db(calc_sheet_info.order_no)
        debit_data = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Доход', calc_row_delete_from_sol=0, calc_row_is_fixed_as_planned=0)
        credit_data = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Расход', calc_row_delete_from_sol=0, calc_row_is_fixed_as_planned=0)
        debit_total_sum, credit_total_sum = calc_ttl_sum_for_calc_sheet_rows(debit_data), calc_ttl_sum_for_calc_sheet_rows(credit_data)
        margin, margin_prcnt = calc_margin_for_calc_sheet(debit_total_sum, credit_total_sum)
        clients_data, article_services_data = fetch_clients_and_services_data_from_db()
        add_names_to_rows(clients_data, article_services_data, debit_data)
        add_names_to_rows(clients_data, article_services_data, credit_data)
        _, pdf_bytes = make_pdf(calc_sheet_info, order_data, debit_total_sum, credit_total_sum, margin, margin_prcnt, debit_data, credit_data)

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename={calc_sheet_info.order_no}.pdf'
        return response
    except Exception as e:
        logger.error(''.join(traceback.format_exception(type(e), value=e, tb=e.__traceback__, chain=False, limit=4)))
        messages.add_message(request, messages.ERROR, _("Не удалось скачать ПДФ. Обратитесь на почту m.golovanov@uk-swift.ru."))
        return redirect('calculation_sheet:view_info', calc_sheet_info.id)


@login_required(login_url='accounts:login')
def sbis_create_task(request, id):
    """ Создаем задачу в Сбисе """
    
    try:
        # Получаем данные расчетного листа
        calc_sheet_info = CalculationSheet.objects.get(id=id)
        order_data = fetch_order_data_from_db(calc_sheet_info.order_no)
        debit_data = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Доход', calc_row_is_fixed_as_planned=0)
        credit_data = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_type='Расход', calc_row_is_fixed_as_planned=0)
        debit_total_sum, credit_total_sum = calc_ttl_sum_for_calc_sheet_rows(debit_data), calc_ttl_sum_for_calc_sheet_rows(credit_data)
        margin, margin_prcnt = calc_margin_for_calc_sheet(debit_total_sum, credit_total_sum)
        clients_data, article_services_data = fetch_clients_and_services_data_from_db()
        add_names_to_rows(clients_data, article_services_data, debit_data)
        add_names_to_rows(clients_data, article_services_data, credit_data)
        pdf, _ = make_pdf(calc_sheet_info, order_data, debit_total_sum, credit_total_sum, margin, margin_prcnt, debit_data, credit_data)   
               
        sbis_href, sbis_doc_id = SbisWorker(request.user).create_approval_for_calc_list(calc_sheet_info.order_no, pdf)

        calc_sheet_info.sbis_href = sbis_href
        calc_sheet_info.sbis_doc_id = sbis_doc_id
        calc_sheet_info.sbis_approval_status = 'Задача в процессе согласования'
        calc_sheet_info.save()
        
    except Exception as e:
        logger.error(''.join(traceback.format_exception(type(e), value=e, tb=e.__traceback__, chain=False, limit=4)))
        messages.add_message(request, messages.ERROR, _("Не удалось создать задачу в Сбис. Обратитесь на почту m.golovanov@uk-swift.ru."))
    return redirect('calculation_sheet:view_info', calc_sheet_info.id)

@login_required(login_url='accounts:login')
def sol_upload_calc_sheet_to_sol(request, id):
    
    calc_sheet_info = CalculationSheet.objects.get(id=id)
    calc_sheet_rows = CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_is_fixed_as_planned=0)
    json_data, i, rows_ids = [], -1, {}
    for calc_sheet_row in calc_sheet_rows:
        if calc_sheet_row.calc_row_original_id is None:
            json_data.append({
                "id": i,
                "orderNo": calc_sheet_info.order_no,
                "feeName": int(calc_sheet_row.calc_row_service_name),
                "fobCifName": calc_sheet_row.calc_row_settlement_procedure,
                "currencyNo": calc_sheet_row.calc_row_currency,
                "countUnit": calc_sheet_row.calc_row_measure,
                "count": calc_sheet_row.calc_row_count,
                "amountSingle": str(calc_sheet_row.calc_row_single_amount),
                "payCustomerName": None if calc_sheet_row.calc_row_type == 'Доход' else int(calc_sheet_row.calc_row_contragent),
                "recCustomerName": int(calc_sheet_row.calc_row_contragent) if calc_sheet_row.calc_row_type == 'Доход' else None,
                "departureStationName": calc_sheet_row.calc_row_departure_station,
                "destinationStationName": calc_sheet_row.calc_row_destination_station,
                "remark": "",
                "createdBy": ""
            })
            rows_ids[i] = calc_sheet_row.id
            i -= 1
        elif calc_sheet_row.calc_row_original_id is not None and calc_sheet_row.calc_row_need_update_in_sol == 1:
            json_data.append({
                "id": calc_sheet_row.calc_row_original_id,
                "orderNo": calc_sheet_info.order_no,
                "feeName": int(calc_sheet_row.calc_row_service_name),
                "fobCifName": calc_sheet_row.calc_row_settlement_procedure,
                "currencyNo": calc_sheet_row.calc_row_currency,
                "countUnit": calc_sheet_row.calc_row_measure,
                "count": calc_sheet_row.calc_row_count,
                "amountSingle": str(calc_sheet_row.calc_row_single_amount),
                "payCustomerName": None if calc_sheet_row.calc_row_type == 'Доход' else int(calc_sheet_row.calc_row_contragent),
                "recCustomerName": int(calc_sheet_row.calc_row_contragent) if calc_sheet_row.calc_row_type == 'Доход' else None,
                "departureStationName": calc_sheet_row.calc_row_departure_station,
                "destinationStationName": calc_sheet_row.calc_row_destination_station,
                "remark": "",
                "createdBy": "",
                "deleteFlag": 0
            })
        elif calc_sheet_row.calc_row_original_id is not None and calc_sheet_row.calc_row_delete_from_sol == 1:
            json_data.append({
                "id": calc_sheet_row.calc_row_original_id,
                "deleteFlag": 1
            })
    try:
        # status_code, api_response, calc_sheet_ids = SolWorker(request.user).upload_calc_rows(json_data, rows_ids)
        status_code, api_response, calc_sheet_ids = 200, {'returnCode': 200}, {}
    except SolIncorrectAuthDataException:
        messages.add_message(request, messages.ERROR, _('Некорректные логин/пароль для СОЛа! Укажите верные в профиле.'))
    except Exception:
        messages.add_message(request, messages.ERROR, _(f'Ошибка при создании р/л по заявке {calc_sheet_info.order_no}. Обратитесь на почту m.golovanov@uk-swift.ru'))
        logger.error(f'Ошибка при создании р/л по заявке {calc_sheet_info.order_no}: {status_code} {api_response}')
    else:
        if status_code == 200 and api_response['returnCode'] == 200:
            messages.add_message(request, messages.SUCCESS, _('Успешно загрузили расчетный лист в СОЛ!'))
            try:
                if not CalculationSheetRow.objects.filter(calculation_sheet_id=id, calc_row_is_fixed_as_planned=1).exists():
                    for calc_sheet_row in calc_sheet_rows:
                        calc_sheet_row.pk = None
                        calc_sheet_row.calc_row_is_fixed_as_planned = 1
                        calc_sheet_row.save()
            except:
                pass
            try:
                for calc_sheet_row in calc_sheet_rows:
                    if calc_sheet_row.calc_row_original_id is None:
                        calc_sheet_row.calc_row_original_id = calc_sheet_ids[calc_sheet_row.id]
                        calc_sheet_row.save()
                    elif calc_sheet_row.calc_row_original_id is not None and calc_sheet_row.calc_row_need_update_in_sol == 1:
                        calc_sheet_row.calc_row_need_update_in_sol = 0
                        calc_sheet_row.save()
                    elif calc_sheet_row.calc_row_original_id is not None and calc_sheet_row.calc_row_delete_from_sol == 1:
                        calc_sheet_row.delete()
                if calc_sheet_info.uploaded_at_sol == 'Нет':
                    calc_sheet_info.uploaded_at_sol = 'Да'
                    calc_sheet_info.save()
            except Exception as e:
                logger.error(f'Ошибка при сохранении данных р/л в БД. order_no: {calc_sheet_info.order_no}, {status_code} {api_response}')
                logger.error(f'calc_sheet_ids: {calc_sheet_ids}')
                logger.error(''.join(traceback.format_exception(type(e), value=e, tb=e.__traceback__, chain=False, limit=4)))
        else:
            messages.add_message(request, messages.ERROR, _(f'Ошибка при создании р/л по заявке {calc_sheet_info.order_no}. Обратитесь на почту m.golovanov@uk-swift.ru'))
            logger.error(f'Ошибка при создании р/л по заявке {calc_sheet_info.order_no}: {status_code} {api_response}')
        
    return redirect('calculation_sheet:view_info', calc_sheet_info.id)