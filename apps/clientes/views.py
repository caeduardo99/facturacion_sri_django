import re
import requests

from decouple import config
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect

from .models import Cliente


SRI_RUC_URL = "https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/obtenerPorNumerosRuc"

# Servicio externo para consultar personas por cédula.
# La URL y el token se configuran en .env.
CEDULA_API_URL = config("CEDULA_API_URL", default="https://consultas.ec/persona/{cedula}")
CEDULA_API_TOKEN = config("CEDULA_API_TOKEN", default="")


def normalizar_identificacion(valor):
    return re.sub(r"\D", "", valor or "")


def consultar_ruc(ruc):
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
        return None, "No se encontró información para ese RUC."

    nombre = (
        data.get("razonSocial")
        or data.get("nombreRazonSocial")
        or data.get("razonSocialNombre")
        or data.get("nombreComercial")
        or ""
    )
    estado = data.get("estadoContribuyenteRuc") or data.get("estado") or ""

    return {
        "identificacion": ruc,
        "ruc": ruc,
        "nombres": nombre,
        "estado": estado,
        "direccion": data.get("direccion") or data.get("direccionMatriz") or "",
        "telefono": data.get("telefono") or "",
        "email": data.get("email") or data.get("correo") or "",
        "fuente": "SRI",
    }, None


def consultar_cedula(cedula):
    url = "http://181.198.254.69:91/api/consultar-identificacion/"

    try:
        response = requests.get(
            url,
            params={"numero": cedula},
            timeout=10,
            headers={
                "Accept": "application/json",
                "User-Agent": "FacturaEC/1.0",
            },
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return None, "No fue posible conectarse con el servicio de consulta de cédulas."
    except ValueError:
        return None, "El servicio de consulta de cédulas respondió con un formato no válido."

    # Respuesta del servicio:
    # {
    #   "contribuyente": {
    #       "identificacion": "...",
    #       "nombreComercial": "..."
    #   }
    # }
    contribuyente = data.get("contribuyente") if isinstance(data, dict) else None

    if not isinstance(contribuyente, dict):
        return None, "No se encontró información para esa cédula."

    identificacion = (
        contribuyente.get("identificacion")
        or cedula
    )

    nombre = (
        contribuyente.get("denominacion")
        or contribuyente.get("nombreComercial")
        or ""
    )

    if not nombre:
        return None, "La consulta no devolvió el nombre del contribuyente."

    return {
        "identificacion": identificacion,
        "ruc": identificacion + "001",
        "nombres": nombre,
        "estado": contribuyente.get("estado") or "",
        "direccion": contribuyente.get("direccionMatriz") or "",
        "telefono": "",
        "email": "",
        "fuente": "Consulta de identificación",
    }, None


def consultar_identificacion(identificacion):
    identificacion = normalizar_identificacion(identificacion)

    if len(identificacion) == 10:
        return consultar_cedula(identificacion)

    if len(identificacion) == 13:
        return consultar_ruc(identificacion)

    return None, "Ingresa una cédula de 10 dígitos o un RUC de 13 dígitos."


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
    datos, error = consultar_identificacion(identificacion)

    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)

    return JsonResponse({"ok": True, "cliente": datos})


@login_required
def editar(request, pk):
    cliente = Cliente.objects.get(pk=pk)

    if request.method == "POST":
        identificacion = normalizar_identificacion(request.POST.get("identificacion"))
        tipo = request.POST.get("tipo_identificacion", "05")
        nombres = request.POST.get("nombres", "").strip()

        if not identificacion or not nombres:
            return render(request, "clientes/editar.html", {
                "cliente": cliente,
                "error": "La identificación y el nombre son obligatorios.",
            })

        cliente.tipo_identificacion = tipo
        cliente.identificacion = identificacion
        cliente.nombres = nombres
        cliente.direccion = request.POST.get("direccion", "").strip()
        cliente.telefono = request.POST.get("telefono", "").strip()
        cliente.email = request.POST.get("email", "").strip()
        cliente.save()

        return redirect("clientes:lista")

    return render(request, "clientes/editar.html", {"cliente": cliente})


@login_required
def eliminar(request, pk):
    cliente = Cliente.objects.get(pk=pk)

    if request.method == "POST":
        cliente.activo = False
        cliente.save(update_fields=["activo", "actualizado"])
        return redirect("clientes:lista")

    return render(request, "clientes/eliminar.html", {"cliente": cliente})


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
