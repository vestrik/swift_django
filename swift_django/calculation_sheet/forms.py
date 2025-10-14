from .models import CalculationSheetRow, CalculationSheet
from django.forms import ModelForm, CharField, TextInput

class CalculationSheetRowDebitForm(ModelForm):
    calc_row_type = CharField(initial='Доход')
    calc_row_contragent = CharField(widget=TextInput(attrs={'placeholder': 'Начните вводить для поиска'}), required=True)
    calc_row_service_name = CharField(widget=TextInput(attrs={'placeholder': 'Начните вводить для поиска'}), required=True)
    
    class Meta:        
        model = CalculationSheetRow
        fields = ['calc_row_type', 'calc_row_contragent', 'calc_row_service_name', 'calc_row_currency', 'calc_row_count', 
                  'calc_row_single_amount', 'calc_row_exchange_rate', 'calc_row_measure', 'calc_row_settlement_procedure', 
                  'calc_row_departure_station', 'calc_row_destination_station']
        
class CalculationSheetRowCreditForm(ModelForm):
    calc_row_type = CharField(initial='Расход')
    calc_row_contragent = CharField(widget=TextInput(attrs={'placeholder': 'Начните вводить для поиска'}), required=True)
    calc_row_service_name = CharField(widget=TextInput(attrs={'placeholder': 'Начните вводить для поиска'}), required=True)
    
    class Meta:
        model = CalculationSheetRow
        fields = ['calc_row_type', 'calc_row_contragent', 'calc_row_service_name', 'calc_row_currency', 'calc_row_count', 
                  'calc_row_single_amount', 'calc_row_exchange_rate', 'calc_row_measure', 'calc_row_settlement_procedure',
                  'calc_row_departure_station', 'calc_row_destination_station']
        

class CalculationSheetForm(ModelForm):    
    order_no = CharField(widget=TextInput(attrs={'placeholder': 'Начните вводить для поиска'}))
    
    class Meta:
        model = CalculationSheet
        fields = ['order_no',]            
        