import django_filters
from django_filters import CharFilter

from .models import CalculationSheet

SBIS_APPROVAL_STATUS_CHOICES = {
    'нет задачи в Сбис на согласование': 'нет задачи в Сбис на согласование',
    'cоздана задача в Сбис (черновик)': 'cоздана задача в Сбис (черновик)',
    'задача в процессе согласования': 'задача в процессе согласования',
    'задача согласована': 'задача согласована',
    'задача не согласована': 'задача не согласована',
}

class CalculationSheetFilter(django_filters.FilterSet):
    calc_sheet_no = CharFilter(field_name='calc_sheet_no', lookup_expr='icontains')
    sbis_approval_status = django_filters.ChoiceFilter(choices=SBIS_APPROVAL_STATUS_CHOICES)
    class Meta:
        model = CalculationSheet
        fields = ('order_no', 'calc_sheet_no', 'sbis_approval_status')