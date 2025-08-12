from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ObjectDoesNotExist

from .forms import UserProfileForm
from .models import UserProfile

# Create your views here.

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request,user)
            return redirect('calculation_sheet:home')
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form':form})


def logout_view(request):    
    logout(request)
    return redirect('calculation_sheet:home')


def profile(request):
    try:
        profile = UserProfile.objects.get(user=request.user.id)
    except ObjectDoesNotExist:
        profile = None
    if request.method == 'POST':
        profile_form = UserProfileForm(request.POST, instance=profile)
        if profile_form.is_valid():
            profile_form_instance = profile_form.save(commit=False)
            profile_form_instance.user = request.user
            profile_form_instance.save()
        return redirect('accounts:profile')
    else:        
        profile_form = UserProfileForm(instance=profile)    
        return render(request, 'accounts/profile.html', {'profile_form': profile_form})