import logging
from django.utils import timezone
import traceback

from .view_functions import make_pdf, django_get_calc_sheet_data
from .models import CalculationSheet, CalculationSheetRow, CalculationSheetPdf

from swift_django.celery import app

logger = logging.getLogger('app.tasks')

    
@app.task(bind=True, name='calc_sheet_save_sol_data', default_retry_delay=60, max_retries=2)
def task__calc_sheet_save_sol_data(self, calc_sheet_id, calc_sheet_rows_sol_ids):
    
    calc_sheet_info = CalculationSheet.objects.get(id=calc_sheet_id)
    calc_sheet_rows = CalculationSheetRow.objects.filter(calculation_sheet_id=calc_sheet_id, calc_row_is_fixed_as_planned=0)
    try:
        for calc_sheet_row in calc_sheet_rows:
            if calc_sheet_row.calc_row_original_id is None:
                calc_sheet_row.calc_row_original_id = calc_sheet_rows_sol_ids[str(calc_sheet_row.id)]
                calc_sheet_row.save()
            elif calc_sheet_row.calc_row_original_id is not None and calc_sheet_row.calc_row_need_update_in_sol == 1:
                calc_sheet_row.calc_row_need_update_in_sol = 0
                calc_sheet_row.save()
            elif calc_sheet_row.calc_row_original_id is not None and calc_sheet_row.calc_row_delete_from_sol == 1:
                calc_sheet_row.delete()

        if calc_sheet_info.uploaded_at_sol == 'Нет':
            calc_sheet_info.uploaded_at_sol = 'Да'
            calc_sheet_info.save()
        logger.info(f'Успешно сохранили в БД данные из СОЛа по заявке {calc_sheet_info.order_no}.')
    except Exception as e:
        logger.error(f'Ошибка при сохранении данных р/л в БД. order_no: {calc_sheet_info.order_no}, calc_sheet_ids: {calc_sheet_rows_sol_ids}')
        logger.error(''.join(traceback.format_exception(type(e), value=e, tb=e.__traceback__, chain=False, limit=4)))
        raise self.retry(exc=e)


@app.task(bind=True, name='fix_planned_calc_sheet', default_retry_delay=60, max_retries=2)
def task__fix_planned_calc_sheet(self, calc_sheet_id):
    """ Фиксируем плановый расчетный лист """
    
    try:
        calc_sheet_rows = CalculationSheetRow.objects.filter(calculation_sheet_id=calc_sheet_id, calc_row_is_fixed_as_planned=0)
        for calc_sheet_row in calc_sheet_rows:
            calc_sheet_row.pk = None
            calc_sheet_row.calc_row_is_fixed_as_planned = 1
            calc_sheet_row.save()
        logger.info(f'Успешно сохранили плановый р/л. calc_sheet_id: {calc_sheet_id}')
    except Exception as e:
        logger.error(f'Ошибка при сохранении планового р/л. calc_sheet_id: {calc_sheet_id}, rows: {calc_sheet_rows}')
        logger.error(''.join(traceback.format_exception(type(e), value=e, tb=e.__traceback__, chain=False, limit=4)))
        raise self.retry(exc=e)


@app.task(bind=True, name='save_pdf_to_db', default_retry_delay=60, max_retries=2)
def task__save_pdf_to_db(self, user, calc_sheet_id, pdf_type):
    logger.info('start')
    try:
        if pdf_type == 'planned':
            calc_row_is_fixed_as_planned = 1
        elif pdf_type == 'actual':
            calc_row_is_fixed_as_planned = 0
        calc_sheet_dict_info = django_get_calc_sheet_data(calc_sheet_id, calc_row_is_fixed_as_planned)
        if calc_sheet_dict_info['calc_sheet_info'].order_no == None:
            calc_sheet_dict_info['calc_sheet_info'].order_no = ''
        __, pdf_bytes = make_pdf(calc_sheet_dict_info)

        calc_sheet_pdf, is_created = CalculationSheetPdf.objects.get_or_create(calculation_sheet=calc_sheet_dict_info['calc_sheet_info'])
        if is_created:
            calc_sheet_pdf.created_by = str(user)
            calc_sheet_pdf.created_at = timezone.now()
        calc_sheet_pdf.edited_by = str(user)
        calc_sheet_pdf.edited_at = timezone.now()
        if pdf_type == 'planned':
            calc_sheet_pdf.planned_calc_sheet_pdf_bytes = pdf_bytes
        elif pdf_type == 'actual':
            calc_sheet_pdf.actual_calc_sheet_pdf_bytes = pdf_bytes
        calc_sheet_pdf.save()
        logger.info(f'Успешно сохранили в БД pdf (тип={pdf_type}) по заявке {calc_sheet_dict_info['calc_sheet_info'].order_no}!')
    except Exception as e:
        logger.error(f'Ошибка при сохранении в БД pdf по заявке (тип={pdf_type}) {calc_sheet_dict_info['calc_sheet_info'].order_no}. pdf_type: {pdf_type}')
        logger.error(''.join(traceback.format_exception(type(e), value=e, tb=e.__traceback__, chain=False, limit=4)))
        raise self.retry(exc=e)