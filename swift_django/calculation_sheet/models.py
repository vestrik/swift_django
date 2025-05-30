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

class CalculationSheet(models.Model):
    author = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)
    slug = models.SlugField(max_length=200, editable=False)
    order_no = models.CharField(max_length=100, blank=False, null=True)
    calc_sheet_no = models.CharField(max_length=100, blank=False, null=True)
    
    def __str__(self):
        return self.order_no
    
    def save(self, *args, **kwargs):
        self.slug = slugify(f'{self.order_no}_{self.calc_sheet_no}', allow_unicode=True)
        super(CalculationSheet, self).save(*args, **kwargs)
        
    class Meta:
        verbose_name = 'Расчетный лист'
        verbose_name_plural = 'Расчетный лист'

    
class CalculationSheetRow(models.Model):
    author = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)
    calculation_sheet = models.ForeignKey(CalculationSheet, on_delete=models.DO_NOTHING, null=True)
    calc_row_type = models.CharField(max_length=100, blank=False, choices=CALC_ROW_TYPE_CHOICES)
    calc_row_contragent = models.CharField(max_length=500)
    calc_row_service_name = models.CharField(max_length=200)
    calc_row_currency = models.CharField(max_length=3, blank=False, choices=CURRENCY_CHOICES)
    calc_row_count = models.PositiveIntegerField()
    calc_row_single_amount = models.DecimalField(max_digits=10, decimal_places=2)
    calc_row_has_nds = models.CharField(max_length=1, choices=HAS_NDS_CHOICES, blank=False)
    calc_row_ttl_nds_price = models.DecimalField(max_digits=10, decimal_places=2)
    calc_row_ttl_price_without_nds = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return f'{self.calculation_sheet} {CalculationSheet.objects.get(id=self.calculation_sheet_id).calc_sheet_no} {self.calc_row_type} {self.calc_row_contragent}'
    
    class Meta:
        verbose_name = 'Доход/Расход'
        verbose_name_plural = 'Доход/Расход'
    
