from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from .models import Producto

def decimal_value(value, default="0"):
    try:
        return Decimal(value or default)
    except (InvalidOperation, ValueError):
        return None

@login_required
def lista(request):
    return render(request, "productos/lista.html", {"productos": Producto.objects.filter(activo=True)})

@login_required
def nuevo(request):
    if request.method == "POST":
        codigo=request.POST.get("codigo","").strip()
        nombre=request.POST.get("nombre","").strip()
        precio=decimal_value(request.POST.get("precio"))
        iva=decimal_value(request.POST.get("porcentaje_iva"),"15")
        stock=decimal_value(request.POST.get("stock"))
        if not codigo or not nombre:
            return render(request,"productos/nuevo.html",{"error":"El código y el nombre son obligatorios.","form":request.POST})
        if precio is None or iva is None or stock is None:
            return render(request,"productos/nuevo.html",{"error":"Precio, IVA y stock deben contener valores numéricos válidos.","form":request.POST})
        Producto.objects.create(codigo=codigo,codigo_auxiliar=request.POST.get("codigo_auxiliar","").strip(),nombre=nombre,descripcion=request.POST.get("descripcion","").strip(),precio=precio,porcentaje_iva=iva,stock=stock)
        return redirect("productos:lista")
    return render(request,"productos/nuevo.html")

@login_required
def editar(request, pk):
    producto=get_object_or_404(Producto,pk=pk)
    if request.method=="POST":
        codigo=request.POST.get("codigo","").strip()
        nombre=request.POST.get("nombre","").strip()
        precio=decimal_value(request.POST.get("precio"))
        iva=decimal_value(request.POST.get("porcentaje_iva"),"15")
        stock=decimal_value(request.POST.get("stock"))
        if not codigo or not nombre:
            return render(request,"productos/editar.html",{"producto":producto,"error":"El código y el nombre son obligatorios."})
        if precio is None or iva is None or stock is None:
            return render(request,"productos/editar.html",{"producto":producto,"error":"Precio, IVA y stock deben contener valores numéricos válidos."})
        producto.codigo=codigo
        producto.codigo_auxiliar=request.POST.get("codigo_auxiliar","").strip()
        producto.nombre=nombre
        producto.descripcion=request.POST.get("descripcion","").strip()
        producto.precio=precio
        producto.porcentaje_iva=iva
        producto.stock=stock
        producto.save()
        return redirect("productos:lista")
    return render(request,"productos/editar.html",{"producto":producto})

@login_required
def eliminar(request, pk):
    producto=get_object_or_404(Producto,pk=pk)
    if request.method=="POST":
        producto.activo=False
        producto.save(update_fields=["activo"])
        return redirect("productos:lista")
    return render(request,"productos/eliminar.html",{"producto":producto})
