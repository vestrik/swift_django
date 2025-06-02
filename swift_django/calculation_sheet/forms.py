from .models import CalculationSheetRow, CalculationSheet
from django.forms import ModelForm, CharField, TextInput, IntegerField, DecimalField, ChoiceField

class CalculationSheetRowDebitForm(ModelForm):
    calc_row_type = CharField(initial='Доход')
    calc_row_contragent = CharField(widget=TextInput(attrs={'placeholder': 'Начните вводить для поиска'}), required=True)
    calc_row_service_name = CharField(widget=TextInput(attrs={'placeholder': 'Начните вводить для поиска'}), required=True)
    
    class Meta:        
        model = CalculationSheetRow
        fields = ['calc_row_type', 'calc_row_contragent', 'calc_row_service_name', 'calc_row_currency', 'calc_row_count', 
                  'calc_row_single_amount', 'calc_row_exchange_rate', 'calc_row_has_nds', 'calc_row_ttl_nds_price', 'calc_row_ttl_price_without_nds']
        
class CalculationSheetRowCreditForm(ModelForm):
    calc_row_type = CharField(initial='Расход')
    calc_row_contragent = CharField(widget=TextInput(attrs={'placeholder': 'Начните вводить для поиска'}), required=True)
    calc_row_service_name = CharField(widget=TextInput(attrs={'placeholder': 'Начните вводить для поиска'}), required=True)
    
    class Meta:
        model = CalculationSheetRow
        fields = ['calc_row_type', 'calc_row_contragent', 'calc_row_service_name', 'calc_row_currency', 'calc_row_count', 
                  'calc_row_single_amount', 'calc_row_exchange_rate', 'calc_row_has_nds', 'calc_row_ttl_nds_price', 'calc_row_ttl_price_without_nds']
        

class CalculationSheetForm(ModelForm):    
    order_no = CharField(widget=TextInput(attrs={'placeholder': 'Начните вводить для поиска'}))
    
    class Meta:
        model = CalculationSheet
        fields = ['order_no', 'calc_sheet_no']            
        