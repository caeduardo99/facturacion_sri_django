from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Empresa

@login_required
def lista(request):
    return render(request, "empresas/lista.html", {"empresas": Empresa.objects.all()})
