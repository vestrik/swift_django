import logging
import json
import traceback
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render, redirect
from django.forms import  inlineformset_factory, modelformset_factory
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from celery import chain

from .filters import CalculationSheetFilter
from .forms import CalculationSheetForm, CalculationSheetRowDebitForm, CalculationSheetRowCreditForm
from .models import CalculationSheet, CalculationSheetRow
from .sbis_worker import SbisWorker
from .sol_worker import SolWorker, SolIncorrectAuthDataException
from .tasks import task__calc_sheet_save_sol_data, task__fix_planned_calc_sheet, task__save_pdf_to_db
from .view_functions import fetch_orders_from_db, fetch_clients_and_services_data_from_db, fetch_order_data_from_db, process_rows_formset, make_pdf, django_get_calc_sheet_data

logger = logging.getLogger(__name__)

def check_if_calc_sheet_exists(request):
    """ Проверяем, существует ли расчетный лист по заявке """
    
    job_num = request.POST.get('job_num', None)
    try:
        CalculationSheet.objects.get(order_no=job_num)
        return_data = {'already_exists': 'true'}
    except ObjectDoesNotExist:
        return_data = {'already_exists': 'false'}
    
    return JsonResponse(return_data)

def fetch_data_for_order(request):
    """ AJAX-ом получаем данные заявки и отдаем для рендера """
    
    job_num = request.POST.get('job_num', None)
    return_data = fetch_order_data_from_db(job_num)
    return JsonResponse(return_data)


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

@login_required(login_url='accounts:login')
def view_info(request, id):
    """ Просмотр расчетного листа """
    
    calc_sheet_dict_info = django_get_calc_sheet_data(calc_sheet_id=id, calc_row_is_fixed_as_planned=0)

    if calc_sheet_dict_info['calc_sheet_info'].order_no == None:
        calc_sheet_dict_info['calc_sheet_info'].order_no = ''
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
            if debit_row_formset.is_valid() and credit_row_formset.is_valid():
                calc_sheet_form.save()
                if debit_row_formset.has_changed():
                    process_rows_formset(request, debit_row_formset, calc_sheet_id=id, need_deletion=True)
                if credit_row_formset.has_changed():
                    process_rows_formset(request, credit_row_formset, calc_sheet_id=id, need_deletion=True)
                return redirect('calculation_sheet:view_info', id)
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
    
@login_required(login_url='accounts:login')
def download_pdf(request, id):
    try: 
        calc_sheet_dict_info = django_get_calc_sheet_data(calc_sheet_id=id, calc_row_is_fixed_as_planned=0)
        __, pdf_bytes = make_pdf(calc_sheet_dict_info)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        calc_sheet_info = calc_sheet_dict_info['calc_sheet_info']
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
        calc_sheet_dict_info = django_get_calc_sheet_data(calc_sheet_id=id, calc_row_is_fixed_as_planned=0)
        pdf, _ = make_pdf(calc_sheet_dict_info)   
        calc_sheet_info = calc_sheet_dict_info['calc_sheet_info']
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
def sol_upload_calc_sheet_to_sol(request, calc_sheet_id):
    
    calc_sheet_info = CalculationSheet.objects.get(id=calc_sheet_id)
    calc_sheet_rows = CalculationSheetRow.objects.filter(calculation_sheet_id=calc_sheet_id, calc_row_is_fixed_as_planned=0)
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
        status_code, api_response, calc_sheet_rows_sol_ids = SolWorker(request.user).upload_calc_rows(json_data, rows_ids)
    except SolIncorrectAuthDataException:
        messages.add_message(request, messages.ERROR, _('Некорректные логин/пароль для СОЛа! Укажите верные в профиле.'))
    except Exception:
        messages.add_message(request, messages.ERROR, _(f'Ошибка при создании р/л по заявке {calc_sheet_info.order_no}. Обратитесь на почту m.golovanov@uk-swift.ru'))
        logger.error(f'Ошибка при создании р/л по заявке {calc_sheet_info.order_no}: {status_code} {api_response}')
    else:
        if status_code == 200 and api_response['returnCode'] == 200:
            messages.add_message(request, messages.SUCCESS, _('Успешно загрузили расчетный лист в СОЛ!'))
            logger.info(f'Успешно загрузили р/л по заявке  {calc_sheet_info.order_no}. calc_sheet_ids: {calc_sheet_rows_sol_ids}')
            if not CalculationSheetRow.objects.filter(calculation_sheet_id=calc_sheet_id, calc_row_is_fixed_as_planned=1).exists():
                chain(
                    task__calc_sheet_save_sol_data.si(calc_sheet_id, calc_sheet_rows_sol_ids), 
                    task__fix_planned_calc_sheet.si(calc_sheet_id),
                    task__save_pdf_to_db.si(str(request.user), calc_sheet_id=calc_sheet_id, pdf_type='planned')
                )()
            else:
                chain(
                    task__calc_sheet_save_sol_data.si(calc_sheet_id, calc_sheet_rows_sol_ids), 
                    task__save_pdf_to_db.si(str(request.user), calc_sheet_id=calc_sheet_id, pdf_type='actual')
                )()
        else:
            messages.add_message(request, messages.ERROR, _(f'Ошибка при создании р/л по заявке {calc_sheet_info.order_no}. Обратитесь на почту m.golovanov@uk-swift.ru'))
            logger.error(f'Ошибка при создании р/л по заявке {calc_sheet_info.order_no}: {status_code} {api_response}')
        
    return redirect('calculation_sheet:view_info', calc_sheet_id)