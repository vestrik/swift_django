from django.db import models
from django.utils import timezone
from django.utils.text import slugify

# Create your models here.

HAS_NDS_CHOICES = {
    None: '',
    'Y': 'Y',
    'N': 'N',
}

CALC_ROW_TYPE_CHOICES = {
    None: '',
    'Доход': 'Доход',
    'Расход': 'Расход',
}

CURRENCY_CHOICES = {
    None: '',
    'RUB': 'RUB',
    'CNY': 'CNY',
    'USD': 'USD',    
    'EUR': 'EUR',
    'KZT': 'KZT',    
}

MEASURE_CHOICES = {
    None: '',
    'декларация': 'декларация',
    'контейнер': 'контейнер',
    'KGS': 'KGS',
    'TEU': 'TEU',
    'Тонна': 'Тонна',
    'SETS': 'SETS',
    'CBM': 'CBM',
    '托': '托',
    'MT': 'MT',
    '车': '车',
    '台': '台',
    'DAY': 'DAY',
    'railway carriage': 'railway carriage',
    '45HC': '45HC',
    '20 NEW VAN': '20 NEW VAN',
    '40GP': '40GP',
    '45RH': '45RH',
    '40TR': '40TR',
    '20GP': '20GP',
    '20TK': '20TK',
    '40HC': '40HC',
    '40RH': '40RH',
    '40HCRF': '40HCRF',
    '40HC NEW VAN': '40HC NEW VAN',
    '40HCPW': '40HCPW',
    '40OT': '40OT',
    '40RF': '40RF',
    '20OT': '20OT',
    '20HC': '20HC',
    '20FR': '20FR',
    '40FR': '40FR',
    '40TK': '40TK'
}

SETTLEMENT_PROCEDURE_CHOICES = {
    None: '',
    'PP': 'PP', 
    'CC': 'CC', 
    'PC': 'PC', 
    'CP': 'CP'
}

class CalculationSheet(models.Model):
    author = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)
    slug = models.SlugField(max_length=200, editable=False)
    order_no = models.CharField(max_length=100, blank=False, null=True, unique=True)
    calc_sheet_no = models.CharField(max_length=100, blank=False, null=True)
    sbis_href = models.CharField(max_length=512, blank=True, null=True)
    sbis_doc_id = models.CharField(max_length=256, blank=True, null=True)
    sbis_approval_status = models.CharField(max_length=128, blank=False, null=False, default='нет задачи в Сбис на согласование')
    
    def __str__(self):
        return self.order_no
    
    def save(self, *args, **kwargs):
        self.slug = slugify(f'{self.order_no}_{self.calc_sheet_no}', allow_unicode=True)
        super(CalculationSheet, self).save(*args, **kwargs)
        
    class Meta:
        verbose_name = 'Расчетный лист'
        verbose_name_plural = 'Расчетный лист'

    
class CalculationSheetRow(models.Model):
    created_by = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)
    edited_by = models.CharField(max_length=100)
    edited_at = models.DateTimeField(default=timezone.now)
    calculation_sheet = models.ForeignKey(CalculationSheet, on_delete=models.DO_NOTHING, null=True)
    calc_row_type = models.CharField(max_length=100, blank=False, choices=CALC_ROW_TYPE_CHOICES)
    calc_row_contragent = models.CharField(max_length=500, blank=False)
    calc_row_service_name = models.CharField(max_length=200, blank=False)
    calc_row_currency = models.CharField(max_length=3, blank=False, choices=CURRENCY_CHOICES)
    calc_row_count = models.PositiveIntegerField(blank=False)
    calc_row_single_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=False)
    calc_row_exchange_rate = models.DecimalField(max_digits=10, decimal_places=2, default=1, blank=False)
    calc_row_has_nds = models.CharField(max_length=1, choices=HAS_NDS_CHOICES, blank=False)
    calc_row_ttl_nds_price = models.DecimalField(max_digits=10, decimal_places=2, blank=False)
    calc_row_ttl_price_without_nds = models.DecimalField(max_digits=10, decimal_places=2, blank=False)
    calc_row_measure = models.CharField(max_length=50, blank=False, choices=MEASURE_CHOICES)
    calc_row_settlement_procedure = models.CharField(max_length=10, blank=False, choices=SETTLEMENT_PROCEDURE_CHOICES)
    
    def __str__(self):
        return f'{self.calculation_sheet} {CalculationSheet.objects.get(id=self.calculation_sheet_id).calc_sheet_no} {self.calc_row_type} {self.calc_row_contragent}'
    
    class Meta:
        verbose_name = 'Доход/Расход'
        verbose_name_plural = 'Доход/Расход'
    
