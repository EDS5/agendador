# -*- coding: utf-8 -*-
from django.shortcuts import render, get_object_or_404, render_to_response, redirect
from django.utils.safestring import mark_safe
import time, calendar
from datetime import date, datetime, timedelta
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, HttpResponse
from django.forms.models import modelformset_factory
from django.template import RequestContext, Library
from django.views.decorators import csrf
from agenda.models import *
from agenda.forms import FormReserva
from django import forms
from datetime import date
from material.frontend import urls as frontend_urls


month_names = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
unidade_default = 'ufsc'

def index(request, unidade=unidade_default):
    #titulo = "Agendador UFSC"
    #corpo = "Bem vindo ao Agendador de espaços físicos e equipamentos da UFSC"

    try:
        unidade = Unidade.objects.get(sigla=unidade)
    except Unidade.DoesNotExist:
        try:
            unidade = Unidade.objects.get(sigla="UFSC")
        except Unidade.DoesNotExist:
            return render_to_response("agenda/index.html")
            
    
    unidades = Unidade.objects.filter(unidadePai=unidade)

    espacosFisicos = EspacoFisico.objects.filter(unidade=unidade)
    equipamentos = Equipamento.objects.filter(unidade=unidade)

    year = time.localtime()[0]
    now_year, now_month = time.localtime()[:2]
    lst = []
    # create a list of months for each year, indicating ones that contain entries and current
    for y in [year, year+1]:
        month_list = []
        for n, month in enumerate(month_names):
                month_list.append(dict(n=n+1, name=month_names[n+1]))
        lst.append((y, month_list))

    return render(
        request,
        "agenda/index.html",
        dict(
            unidade=unidade, unidades=unidades,
            espacosfisicos=espacosFisicos, equipamentos=equipamentos,
            years=lst, user=request.user
            )
        )


def sobre(request):
	return render(request, "agenda/sobre.html", {'titulo':titulo})

def ano(request, unidade=None ,year=None):
    # prev / next years
    if year: year = int(year)
    else:    year = time.localtime()[0]
    nowy, nowm = time.localtime()[:2]
    lst = []
    # create a list of months for each year, indicating ones that contain entries and current
    for y in [year, year+1]:
        mlst = []
        for n, month in enumerate(month_names):
            entry = current = False
            if y == nowy and n+1 == nowm:
                current = True
            mlst.append(dict(n=n+1, name=month, current=current))
        lst.append((y, mlst))
    
    espacosfisicos = EspacoFisico.objects.filter(unidade=unidade)

    return render_to_response("ano.html", dict(years=lst, user=request.user, year=year, espacosfisicos=espacosfisicos))

def mes(request, tipo=None, espaco=None, year=None, month=None, change=None):
    """Listing of days in `month`."""
    espaco, year, month = int(espaco), int(year), int(month)
    # apply next / previous change
    if change in ("next", "prev"):
        now, mdelta = date(year, month, 15), timedelta(days=31)
        if change == "next":   mod = mdelta
        elif change == "prev": mod = -mdelta

        year, month = (now+mod).timetuple()[:2]

    # init variables
    cal = calendar.Calendar()
    month_days = cal.itermonthdays(year, month)
    nyear, nmonth, nday = time.localtime()[:3]
    lst = [[]]
    week = 0
    for day in month_days:
        entries = current = False
        if day:
            if tipo=="e":
                if request.user.is_superuser:
                    entries = ReservaEquipamento.objects.filter(data__year=year, data__month=month, data__day=day, equipamento=espaco)
                else:
                    entries = ReservaEquipamento.objects.filter(data__year=year, data__month=month, data__day=day, equipamento=espaco, usuario=request.user)    
            else:
                if request.user.is_superuser:
                    entries = ReservaEspacoFisico.objects.filter(data__year=year, data__month=month, data__day=day, espacoFisico=espaco)
                else:
                    entries = ReservaEspacoFisico.objects.filter(data__year=year, data__month=month, data__day=day, espacoFisico=espaco, usuario=request.user)

        if day == nday and year == nyear and month == nmonth:
            current = True

        lst[week].append((day, entries, current))
        if len(lst[week]) == 7:
            lst.append([])
            week += 1
    if(tipo=="e"):
        espacofisico = Equipamento.objects.get(id=espaco)
    else:
        espacofisico = EspacoFisico.objects.get(id=espaco)
        tipo = 'f'
    return render(
            request,
            "agenda/mes.html", 
            dict(
                espaco=espacofisico, year=year, month=month, 
                user=request.user, month_days=lst, mname=month_names[month-1],
                tipo=tipo
                ))

def mese(request, espaco, year, month, change=None):
    return mes(request, espaco, year, month, change, tipo="e")

def dia(request, espaco, year, month, day):
    """Entries for the day."""
    nyear, nmonth, nday = time.localtime()[:3]
    espacofisico = EspacoFisico.objects.get(id=espaco)
    reservas = ReservaEspacoFisico.objects.filter(data__year=year, data__month=month, data__day=day, espacoFisico=espaco).order_by("horaInicio")
    return render(request, "agenda/dia.html", dict(reservas=reservas, espaco=espacofisico, anovisualizacao=year ,mesvisualizacao=month, dia=day))


def espacos(request):
	espacos1 = EspacoFisico.objects.order_by("nome").all()
	ano = time.localtime()[0]
	mes = time.localtime()[1]
	return render(
            request,
            "agenda/espacos.html",
            dict(ano=ano, mes=mes, espacos=espacos1
                ))

def equipamentos(request):
    espacos1 = Equipamento.objects.order_by("nome").all()
    ano = time.localtime()[0]
    mes = time.localtime()[1]
    return render_to_response("espacos.html", {'ano': ano, 'mes': mes, 'espacos': espacos1})

@login_required
def addreserva(request, espacoatual, ano=None, mes= None, dia=None):
    usuario = request.user.username
    dados = request.session.get('attributes')
    if request.method == "POST":
        request.POST = request.POST.copy()
        request.POST['estado'] = 1
        request.POST['usuario'] = request.user.id
        form = FormReserva(request.POST, request.FILES)
        if form.is_valid():
            form.fields['usuario'] = forms.CharField(initial=request.user.id)
            
            if ((not request.user.groups.filter(name="LABINFO").exists()) and (request.POST['espacoFisico']=='3')):
                return render_to_response("salvo.html",{'mensagem':"Erro: Você não realizaou o curso para utilizar o labinfo "})
            
            if form.choque():
                return render_to_response("salvo.html",{'mensagem':"Erro: Já existe reserva neste horário"})
            
            """Permite somente idufsc do grupo CCS:"""
            if(not request.user.groups.filter(name="CCS").exists()):
                return render_to_response("salvo.html",{'mensagem':"Erro: Você não é membro do grupo CCS! Fale com o Mario!"})

            form.save()
            form.enviarEmail(request.user.email)
            return render_to_response("salvo.html",{'mensagem': "Reserva realizada com sucesso!"})
    else:
        form = FormReserva()
        form.fields['usuario'].widget = forms.HiddenInput()
        form.fields['estado'].widget = forms.HiddenInput()
        form.fields['dataReserva'].widget = forms.HiddenInput()
        espacoatuala = EspacoFisico.objects.filter(id=espacoatual)
        #print "aquiii"
        #print espacoatuala
        form.fields['espacoFisico'].queryset = espacoatuala
        form.fields['espacoFisico'].initial = espacoatuala[0].id
        form.fields['evento'].queryset = espacoatuala[0].eventosPermitidos
        if ano and mes and dia:
            form.fields['data'].initial = date(int(ano), int(mes), int(dia))
        choices = (("8:00","8:00"),("9:00","9:00"))
        form.fields['horaInicio'].choices = choices
        #form.fields['horaInicio'] = forms.ChoiceField(choices)

    return render(request, "addreserva.html", {'form': form, "usuario": usuario, 'dados': dados })

def intermediaria(request, id_equip, data_numero):
    request.session['id_equip'] = id_equip
    data_string = str(data_numero)
    data = data_string[0]+data_string[1]+'/'+data_string[2]+data_string[3]+'/'+data_string[4]+data_string[5]+data_string[6]+data_string[7]
    request.session['data'] = data
    return redirect('/adminagenda/reservaequipamento/add/')
