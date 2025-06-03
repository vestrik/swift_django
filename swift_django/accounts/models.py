from django.db import models
from django.contrib.auth.models import User

# Create your models here.

class UserProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    sbis_login = models.CharField(max_length=256)
    sbis_password = models.CharField(max_length=256)
    sol_login = models.CharField(max_length=256)
    sol_password = models.CharField(max_length=256)
    
    def __str__(self):
        return f'{self.user}'
    
    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'