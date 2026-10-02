import re
import requests

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect

from .models import Cliente


SRI_RUC_URL = "https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/obtenerPorNumerosRuc"


def normalizar_identificacion(valor):
    return re.sub(r"\D", "", valor or "")


def consultar_sri(identificacion):
    identificacion = normalizar_identificacion(identificacion)

    if len(identificacion) == 10:
        ruc = identificacion + "001"
    elif len(identificacion) == 13:
        ruc = identificacion
    else:
        return None, "Ingresa una cédula de 10 dígitos o un RUC de 13 dígitos."

    try:
        response = requests.get(
            SRI_RUC_URL,
            params={"ruc": ruc},
            timeout=10,
            headers={"Accept": "application/json", "User-Agent": "FacturaEC/1.0"},
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return None, "No fue posible conectarse con el servicio de consulta del SRI."
    except ValueError:
        return None, "El SRI respondió con un formato no válido."

    if isinstance(data, list):
        data = data[0] if data else None

    if not data:
        return None, "No se encontró información para esa identificación."

    # El servicio puede cambiar los nombres de las propiedades.
    nombre = (
        data.get("razonSocial")
        or data.get("nombreRazonSocial")
        or data.get("razonSocialNombre")
        or data.get("nombreComercial")
        or ""
    )
    estado = data.get("estadoContribuyenteRuc") or data.get("estado") or ""

    return {
        "identificacion": identificacion,
        "ruc": ruc,
        "nombres": nombre,
        "estado": estado,
        "direccion": data.get("direccion") or data.get("direccionMatriz") or "",
        "telefono": data.get("telefono") or "",
        "email": data.get("email") or data.get("correo") or "",
        "datos_sri": data,
    }, None


@login_required
def lista(request):
    return render(request, "clientes/lista.html", {
        "clientes": Cliente.objects.filter(activo=True)
    })


@login_required
def nuevo(request):
    return render(request, "clientes/nuevo.html")


@login_required
def consultar(request):
    identificacion = request.GET.get("identificacion", "")
    datos, error = consultar_sri(identificacion)

    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)

    return JsonResponse({"ok": True, "cliente": datos})


@login_required
def crear(request):
    if request.method != "POST":
        return redirect("clientes:nuevo")

    identificacion = normalizar_identificacion(request.POST.get("identificacion"))
    tipo = request.POST.get("tipo_identificacion", "05")
    nombres = request.POST.get("nombres", "").strip()

    if not identificacion or not nombres:
        return render(request, "clientes/nuevo.html", {
            "error": "La identificación y el nombre son obligatorios.",
            "form": request.POST,
        })

    Cliente.objects.update_or_create(
        identificacion=identificacion,
        defaults={
            "tipo_identificacion": tipo,
            "nombres": nombres,
            "direccion": request.POST.get("direccion", "").strip(),
            "telefono": request.POST.get("telefono", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "activo": True,
        },
    )

    return redirect("clientes:lista")
