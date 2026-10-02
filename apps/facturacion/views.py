from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Comprobante
@login_required
def lista(request): return render(request,'facturacion/lista.html',{'comprobantes':Comprobante.objects.select_related('cliente').order_by('-fecha_emision','-id')})
