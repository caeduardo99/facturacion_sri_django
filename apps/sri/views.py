from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import TransmisionSRI
@login_required
def estado(request): return JsonResponse({'pendientes':TransmisionSRI.objects.filter(estado='PENDIENTE').count(),'recibidas':TransmisionSRI.objects.filter(estado='RECIBIDA').count(),'autorizadas':TransmisionSRI.objects.filter(estado='AUTORIZADO').count()})
