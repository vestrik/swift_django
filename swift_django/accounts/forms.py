from django.forms import ModelForm
from .models import UserProfile

class UserProfileForm(ModelForm):
       
    class Meta:
        model = UserProfile
        fields = ['sbis_login', 'sbis_password', 'sol_login', 'sol_password']
        