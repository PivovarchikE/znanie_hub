from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
from django.core.paginator import Paginator
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from courses import models
from users import models


@require_GET
def index(request):
    return render(request, 'index.html')