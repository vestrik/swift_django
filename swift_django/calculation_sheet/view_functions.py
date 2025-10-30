import base64
from weasyprint import HTML, CSS
from django.utils import timezone
from django.template.loader import render_to_string
from django.db import connections
from decimal import InvalidOperation

from .models import CalculationSheet, CalculationSheetRow


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

def make_pdf(calc_sheet_dict_info):
    """ Создаем ПДФ """

    context = {
        'calc_sheet_info': calc_sheet_dict_info['calc_sheet_info'],
        'order_department': calc_sheet_dict_info['order_data']['department'],
        'order_box': calc_sheet_dict_info['order_data']['box'],
        'order_client': calc_sheet_dict_info['order_data']['client'],
        'order_station_from': calc_sheet_dict_info['order_data']['station_from'],
        'order_station_to': calc_sheet_dict_info['order_data']['station_to'],
        'debit_total_sum': round(calc_sheet_dict_info['debit_total_sum'], 2),
        'credit_total_sum': round(calc_sheet_dict_info['credit_total_sum'], 2),
        'margin_total_sum': calc_sheet_dict_info['margin'],
        'margin_prcnt': calc_sheet_dict_info['margin_prcnt'],
        'calc_sheet_debit_rows': calc_sheet_dict_info['debit_data'],
        'calc_sheet_credit_rows': calc_sheet_dict_info['credit_data']
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

def django_get_calc_sheet_data(calc_sheet_id, calc_row_is_fixed_as_planned):
    calc_sheet_info = CalculationSheet.objects.get(id=calc_sheet_id)    
    order_data = fetch_order_data_from_db(calc_sheet_info.order_no)    
    debit_data = CalculationSheetRow.objects.filter(calculation_sheet_id=calc_sheet_id, calc_row_type='Доход', calc_row_delete_from_sol=0, calc_row_is_fixed_as_planned=calc_row_is_fixed_as_planned)
    credit_data = CalculationSheetRow.objects.filter(calculation_sheet_id=calc_sheet_id, calc_row_type='Расход', calc_row_delete_from_sol=0, calc_row_is_fixed_as_planned=calc_row_is_fixed_as_planned)
    debit_total_sum, credit_total_sum = calc_ttl_sum_for_calc_sheet_rows(debit_data), calc_ttl_sum_for_calc_sheet_rows(credit_data)
    margin, margin_prcnt = calc_margin_for_calc_sheet(debit_total_sum, credit_total_sum)
    clients_data, article_services_data = fetch_clients_and_services_data_from_db()
    add_names_to_rows(clients_data, article_services_data, debit_data)
    add_names_to_rows(clients_data, article_services_data, credit_data)
    
    calc_sheet_dict_info = {
        'calc_sheet_info': calc_sheet_info,
        'order_data': order_data,
        'debit_data': debit_data,
        'credit_data': credit_data,
        'debit_total_sum': debit_total_sum,
        'credit_total_sum': credit_total_sum,
        'margin': margin,
        'margin_prcnt': margin_prcnt,
    }
    return calc_sheet_dict_info