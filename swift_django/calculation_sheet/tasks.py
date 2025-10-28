import logging
import traceback

from swift_django.celery import app
from .models import CalculationSheet, CalculationSheetRow

logger = logging.getLogger('app.tasks')

    
@app.task(bind=True, name='calc_sheet_save_sol_data', default_retry_delay=6, max_retries=2)
def task__calc_sheet_save_sol_data(self, calc_sheet_id, calc_sheet_rows_sol_ids):
    
    calc_sheet_info = CalculationSheet.objects.get(id=calc_sheet_id)
    calc_sheet_rows = CalculationSheetRow.objects.filter(calculation_sheet_id=calc_sheet_id, calc_row_is_fixed_as_planned=0)
    logger.info(calc_sheet_rows_sol_ids)
    try:
        for calc_sheet_row in calc_sheet_rows:
            if calc_sheet_row.calc_row_original_id is None:
                calc_sheet_row.calc_row_original_id = calc_sheet_rows_sol_ids[calc_sheet_row.id]
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
    except Exception as e:
        logger.error(f'Ошибка при сохранении планового р/л. calc_sheet_id: {calc_sheet_id}, rows: {calc_sheet_rows}')
        logger.error(''.join(traceback.format_exception(type(e), value=e, tb=e.__traceback__, chain=False, limit=4)))
        raise self.retry(exc=e)