import re
import requests

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Empresa


SRI_RUC_URL = "https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente/obtenerPorNumerosRuc"


def normalizar_ruc(valor):
    return re.sub(r"\D", "", valor or "")


def consultar_sri_ruc(ruc):
    ruc = normalizar_ruc(ruc)

    if len(ruc) != 13:
        return None, "Ingresa un RUC de 13 dígitos."

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

    if not isinstance(data, dict) or not data:
        return None, "No se encontró información para ese RUC."

    razon_social = (
        data.get("razonSocial")
        or data.get("nombreRazonSocial")
        or data.get("razonSocialNombre")
        or ""
    )
    nombre_comercial = data.get("nombreComercial") or ""
    direccion = data.get("direccionMatriz") or data.get("direccion") or ""

    if not razon_social:
        razon_social = nombre_comercial

    if not razon_social:
        return None, "El SRI no devolvió la razón social del contribuyente."

    return {
        "ruc": ruc,
        "razon_social": razon_social,
        "nombre_comercial": nombre_comercial,
        "direccion_matriz": direccion,
        "obligado_contabilidad": bool(
            data.get("obligadoLlevarContabilidad")
            or data.get("obligadoContabilidad")
            or False
        ),
    }, None


@login_required
def lista(request):
    return render(request, "empresas/lista.html", {
        "empresas": Empresa.objects.filter(activo=True)
    })


@login_required
def nuevo(request):
    return render(request, "empresas/nuevo.html")


@login_required
def consultar(request):
    datos, error = consultar_sri_ruc(request.GET.get("ruc", ""))

    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)

    return JsonResponse({"ok": True, "empresa": datos})


@login_required
def crear(request):
    if request.method != "POST":
        return redirect("empresas:nuevo")

    ruc = normalizar_ruc(request.POST.get("ruc"))
    razon_social = request.POST.get("razon_social", "").strip()

    if len(ruc) != 13 or not razon_social:
        return render(request, "empresas/nuevo.html", {
            "error": "El RUC debe tener 13 dígitos y la razón social es obligatoria.",
            "form": request.POST,
        })

    Empresa.objects.update_or_create(
        ruc=ruc,
        defaults={
            "razon_social": razon_social,
            "nombre_comercial": request.POST.get("nombre_comercial", "").strip(),
            "direccion_matriz": request.POST.get("direccion_matriz", "").strip(),
            "obligado_contabilidad": request.POST.get("obligado_contabilidad") == "on",
            "ambiente_sri": int(request.POST.get("ambiente_sri", "1")),
            "certificado_path": request.POST.get("certificado_path", "").strip(),
            "certificado_password": request.POST.get("certificado_password", "").strip(),
            "activo": True,
        },
    )

    return redirect("empresas:lista")


@login_required
def editar(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)

    if request.method == "POST":
        ruc = normalizar_ruc(request.POST.get("ruc"))
        razon_social = request.POST.get("razon_social", "").strip()

        if len(ruc) != 13 or not razon_social:
            return render(request, "empresas/editar.html", {
                "empresa": empresa,
                "error": "El RUC debe tener 13 dígitos y la razón social es obligatoria.",
            })

        empresa.ruc = ruc
        empresa.razon_social = razon_social
        empresa.nombre_comercial = request.POST.get("nombre_comercial", "").strip()
        empresa.direccion_matriz = request.POST.get("direccion_matriz", "").strip()
        empresa.obligado_contabilidad = request.POST.get("obligado_contabilidad") == "on"
        empresa.ambiente_sri = int(request.POST.get("ambiente_sri", "1"))
        empresa.certificado_path = request.POST.get("certificado_path", "").strip()

        password = request.POST.get("certificado_password", "").strip()
        if password:
            empresa.certificado_password = password

        empresa.save()
        return redirect("empresas:lista")

    return render(request, "empresas/editar.html", {"empresa": empresa})


@login_required
def eliminar(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)

    if request.method == "POST":
        empresa.activo = False
        empresa.save(update_fields=["activo", "actualizado"])
        return redirect("empresas:lista")

    return render(request, "empresas/eliminar.html", {"empresa": empresa})
