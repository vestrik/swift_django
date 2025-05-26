from django.db import models
from django.utils import timezone

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
    created_at = models.DateTimeField(default=timezone.now())
    slug = models.SlugField(max_length=200, editable=False)
    order_no = models.CharField(max_length=100)
    calc_row_type = models.CharField(max_length=100, blank=False, choices=CALC_ROW_TYPE_CHOICES)
    calc_row_contragent = models.CharField(max_length=500)
    calc_row_service_name = models.CharField(max_length=200)
    calc_row_currency = models.CharField(max_length=3, blank=False, choices=CURRENCY_CHOICES)
    calc_row_count = models.PositiveIntegerField()
    calc_row_single_amount = models.DecimalField(max_digits=10, decimal_places=2)
    calc_row_has_nds = models.CharField(max_length=1, choices=HAS_NDS_CHOICES, blank=False)
    calc_row_ttl_nds_price = models.DecimalField(max_digits=10, decimal_places=2)
    calc_row_ttl_price_without_nds = models.DecimalField(max_digits=10, decimal_places=2)
    