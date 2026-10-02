from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Cliente
@login_required
def lista(request): return render(request,'clientes/lista.html',{'clientes':Cliente.objects.filter(activo=True)})
