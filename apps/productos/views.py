from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Producto
@login_required
def lista(request): return render(request,'productos/lista.html',{'productos':Producto.objects.filter(activo=True)})
