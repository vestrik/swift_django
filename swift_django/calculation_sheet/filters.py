import django_filters

from .models import CalculationSheet

SBIS_APPROVAL_STATUS_CHOICES = {
    'нет задачи в Сбис на согласование': 'нет задачи в Сбис на согласование',
    'cоздана задача в Сбис (черновик)': 'cоздана задача в Сбис (черновик)',
    'задача в процессе согласования': 'задача в процессе согласования',
    'задача согласована': 'задача согласована',
    'задача не согласована': 'задача не согласована',
}

class CalculationSheetFilter(django_filters.FilterSet):
    sbis_approval_status = django_filters.ChoiceFilter(choices=SBIS_APPROVAL_STATUS_CHOICES)
    calc_sheet_name = django_filters.CharFilter(field_name='calc_sheet_name', lookup_expr='icontains')
    has_order_no = django_filters.BooleanFilter(field_name='order_no', lookup_expr='isnull', exclude=True)
    
    class Meta:
        model = CalculationSheet
        fields = ('order_no', 'sbis_approval_status', 'calc_sheet_name')