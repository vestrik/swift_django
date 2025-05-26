from .models import CalculationSheet
from django.forms import ModelForm

class CalculationSheetForm(ModelForm):
    class Meta:
        model = CalculationSheet
        fields = ['calc_row_type', 'calc_row_contragent', 'calc_row_service_name', 'calc_row_currency', 'calc_row_count', 
                  'calc_row_single_amount', 'calc_row_has_nds', 'calc_row_ttl_nds_price', 'calc_row_ttl_price_without_nds']