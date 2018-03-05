# -*- coding: utf-8 -*-

from agenda.models import *
from django.contrib import messages
from django.conf import settings
from django import forms
from django.contrib.admin import widgets
import datetime
from datetime import timedelta
from django.core.mail import send_mail
from django.forms import ModelForm, Form, HiddenInput, models, fields
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.contrib.admin import widgets
from django.forms.widgets import Select
from widgets import *
from django.contrib.auth.models import User, Group, Permission
from django.db.models.fields.related import ManyToOneRel
import admin

translated_week_names = dict(Sunday='domingo', Monday='segunda-feira', Tuesday='terça-feira', Wednesday='quarta-feira', Thursday='quinta-feira', Friday='sexta-feira', Saturday='sábado')

class ReservaAdminForm(forms.ModelForm):
    recorrente = forms.BooleanField(required=False)
    dataInicio = forms.DateField(required=False)
    dataFim = forms.DateField(required=False)

    class Meta:
        model = Reserva
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        self.admin_type = kwargs.pop('admin_type', None)
        self.reservable_type = kwargs.pop('reservable_type', None)
        self.reserve_type = kwargs.pop('reserve_type', None)
        super(ReservaAdminForm, self).__init__(*args, **kwargs)
        self.is_new_object = True  # start assuming the form is to create a new object in the db

        # If the user is trying to edit a reserve for a reservable not being responsable for it, he can only read
        # If the user is creating a new reserve or trying to edit a form he has permission, he can change the fields accordingly
        readOnly = False
        if 'instance' in kwargs:
            if kwargs['instance']:
                self.is_new_object = False  # the form is to edit an existing object
                self.instance = kwargs['instance']
                reservable = kwargs['instance'].locavel
                if self.request.user not in reservable.responsavel.all():
                    readOnly = True

        if readOnly and not self.request.user.is_superuser:
            self.init_read_only(kwargs)
        else:
            self.init_status_field(kwargs)
            self.init_date_field()
            self.init_hour_fields()
            self.init_reservable_field(kwargs)
            self.init_activity_field()
            self.init_user_field()
            self.init_recurrent_field(kwargs)

    def init_recurrent_field(self, kwargs):
        self.fields['recorrente'].widget = RecurrentReserveWidget()
        if self.is_new_object:
            self.fields['dataInicio'].widget = forms.HiddenInput()
            self.fields['dataInicio'].label = ''
            self.fields['dataFim'].label = 'Data Fim'
        elif kwargs['instance'].recorrencia:
            instance = kwargs['instance']
            self.fields['dataInicio'].initial = instance.recorrencia.dataInicio
            self.fields['dataInicio'].widget = ReadOnlyWidget(attrs=dict(label='Data início'))
            self.fields['dataInicio'].disabled = True
            self.fields['dataFim'].widget = ReadOnlyWidget(attrs=dict(label='Data fim'))
            self.fields['dataFim'].disabled = True
            self.fields['dataFim'].initial = instance.recorrencia.dataFim
            self.fields['recorrente'].initial = True

    def init_read_only(self, kwargs):
        # For all fields, put the readonly widget and makes sure the data can't be tempered
        self.fields['data'].widget = ReadOnlyWidget()
        self.fields['data'].disabled = True
        self.fields['horaInicio'].widget = ReadOnlyWidget(attrs=dict(label='Hora início'))
        self.fields['horaInicio'].disabled = True
        self.fields['horaFim'].widget = ReadOnlyWidget(attrs=dict(label='Hora fim'))
        self.fields['horaFim'].disabled = True
        self.fields['locavel'].widget = ReadOnlyWidget(attrs=dict(label='Locável'), search_model=type(kwargs['instance'].locavel))
        self.fields['locavel'].disabled = True
        self.fields['atividade'].widget = ReadOnlyWidget(type(kwargs['instance'].atividade))
        self.fields['ramal'].widget = ReadOnlyWidget()
        self.fields['ramal'].disabled = True
        self.fields['finalidade'].widget = ReadOnlyWidget()
        self.fields['finalidade'].disabled = True
        self.fields['recorrente'].widget = ReadOnlyWidget(check_box=True, check_box_value=kwargs['instance'].recorrencia)
        self.fields['recorrente'].disabled = True

        if kwargs['instance'].recorrencia:
            self.fields['dataInicio'].initial = kwargs['instance'].recorrencia.dataInicio
            self.fields['dataInicio'].widget = ReadOnlyWidget()
            self.fields['dataInicio'].label = 'Data início'
            self.fields['dataInicio'].disabled = True
            self.fields['dataFim'].initial = kwargs['instance'].recorrencia.dataFim
            self.fields['dataFim'].widget = ReadOnlyWidget()
            self.fields['dataFim'].disabled= True
        else:
            self.fields['dataInicio'].widget = forms.HiddenInput()
            self.fields['dataInicio'].label = ''
            self.fields['dataFim'].widget = forms.HiddenInput()
            self.fields['dataFim'].label = ''

        # The hidden fields are hidded
        self.fields['estado'].label = ''
        self.fields['estado'].widget = forms.HiddenInput()
        self.fields['usuario'].widget = forms.HiddenInput()
        self.fields['usuario'].label = ''

    def init_status_field(self, kwargs):
        # If we're creating a new form it's okay to hide the status.
        # If we're additing an existing one, it must show status if user is reponsable
        hide = False
        if 'instance' in kwargs:
            if kwargs['instance']:
                reservable = kwargs['instance'].locavel
                # Check what's the model and reservables the user own
                if isinstance(reservable, EspacoFisico):
                    reservable_set = self.request.user.espacofisico_set.all()
                elif isinstance(reservable, Equipamento):
                    reservable_set = self.request.user.equipamento_set.all()
                if reservable not in reservable_set:
                    hide = True
            else:
                hide = True
        else:
            hide = True
        if hide and not self.request.user.is_superuser:
            self.fields['estado'].initial = 'E'
            self.fields['estado'].label = ''
            self.fields['estado'].widget = forms.HiddenInput()

    def init_user_field(self):
        # Hide if it's not superuser, otherwise check for errors and initialize
        if not self.request.user.is_superuser:
            self.fields['usuario'].initial = self.request.user
            self.fields['usuario'].widget = forms.HiddenInput()
            self.fields['usuario'].label = ''
        else:
            attrs = dict(label='Usuário')
            if 'usuario' in self.errors:
                attrs['error'] = self.errors['usuario']
            self.fields['usuario'].widget = AutocompleteWidget(attrs=attrs, query=User.objects.all(), model=User)

    def init_activity_field(self):
        # If there's a initial reservable get activities that belong to it
        if self.fields['locavel'].initial:
            reservable = self.reservable_type.objects.get(id=self.fields['locavel'].initial)
            self.fields['atividade'].queryset = reservable.atividadesPermitidas

        # Initialize the widget that dynamically change activities according to the selected reservable
        rel = Reserva._meta.get_field('atividade').rel
        self.fields['atividade'].widget = DynamicAtividadeWidget(Select(choices=models.ModelChoiceIterator(self.fields['atividade'])), rel, admin.admin.site)
        self.fields['atividade'].widget.can_add_related = False  # remove add button
        self.fields['atividade'].widget.can_change_related = False  # remove edit button

    def init_reservable_field(self, kwargs):
        # If there was a error of validation there's the need to recover the reservable as pre-selected
        if self.errors:
            try:
                self.request.session['id_reservable'] = self.request.session['id_reservable_backup']
            except:
                pass

        # Check if there is a pre-selected reservable
        try:
            self.id_reservable = self.request.session['id_reservable']
        except:
            self.id_reservable = None

        # If user is changing an existing reserve the reserve's reservable already selected is the only option
        # If user is creating a reserve, the queryset of possible reservables is determinet
        if 'instance' in kwargs:
            if kwargs['instance']:
                reservable = kwargs['instance'].locavel
                queryset = self.reservable_type.objects.filter(id=reservable.id)
            else:
                ma = self.admin_type(self.reservable_type, AdminSite())
                queryset = ma.get_queryset(self.request)
        else:
            ma = self.admin_type(self.reservable_type, AdminSite())
            queryset = ma.get_queryset(self.request)

        # If there's a pre=selected reservable he is the option
        # Else the options are the user's queryset
        if self.id_reservable:
            self.fields['locavel'].initial = self.id_reservable
            self.fields['locavel'].queryset = self.reservable_type.objects.filter(id=self.id_reservable)
        else:
            self.fields['locavel'].queryset = queryset

            # id_reservable is saved so it can be recovered in case of validation error
        self.request.session['id_reservable_backup'] = self.id_reservable
        self.request.session['id_reservable'] = None

        self.fields['locavel'].label = 'Locável'  # set label
        self.fields['locavel'].widget.can_add_related = False  # remove add button
        self.fields['locavel'].widget.can_change_related = False  # remove edit button

    def init_hour_fields(self):
        # Check fields for error and intialize Widgets
        attrs = dict(label='Hora início')
        if 'horaInicio' in self.errors:
            attrs['error'] = self.errors['horaInicio']
        self.fields['horaInicio'] = forms.TimeField(input_formats=['%H:%M'], widget=SelectTimeWidget(attrs=attrs))
        attrs = dict(label='Hora fim')
        if 'horaFim' in self.errors:
            attrs['error'] = self.errors['horaFim']
        self.fields['horaFim'] = forms.TimeField(input_formats=['%H:%M'], widget=SelectTimeWidget(attrs=attrs))

        # See if there's a initial value
        try:
            self.fields['horaInicio'].initial = self.request.session['horaInicio']
            self.fields['horaFim'].initial = self.request.session['horaFim']
        except:
            pass

        self.request.session['horaInicio'] = ''
        self.request.session['horaFim'] = ''

    def init_date_field(self):
        # See if there's a initial value
        try:
            self.fields['data'].initial = self.request.session['data']
        except:
            pass
        self.request.session['data'] = ''

    def send_mail(self, status, instance):
        user = instance.usuario
        status = instance.estado
        reservable = instance.locavel
        date = instance.data
        start = instance.horaInicio
        end = instance.horaFim
        responsables = reservable.responsavel.all()

        # add e-mail text that alerts a recurrent reserve
        if self.cleaned_data['recorrente']:
            day_name = instance.recorrencia.dataInicio.strftime("%A")
            translated_day_name = translated_week_names[day_name]
            if translated_day_name == 'sabado' or translated_day_name == 'domingo':
                conector = 'todo'
            else:
                conector = 'toda'
            ending_date = instance.recorrencia.dataFim
            date = instance.recorrencia.dataInicio
            recurrent_text= ' ao dia %s, %s %s' % (ending_date.strftime('%d/%m/%Y'), conector, translated_day_name)
        else:
            recurrent_text = ''

        # First we send an email to the user who asked for the reserve
        if status == 'A':
            email_title = 'Reserva de %s confirmada.' % reservable.nome.encode("utf-8")
            email_text = '''
                Olá, %s,
                Sua reserva de %s para o dia %s%s, das %s às %s, foi confirmada.

                -------
                E-mail automático, por favor não responda.
            ''' % (user, reservable.nome.encode("utf-8"), date.strftime('%d/%m/%Y'), recurrent_text, start.strftime('%H:%M'), end.strftime('%H:%M'))
        elif status == 'E':
            email_title = 'Reserva de %s aguardando aprovação.' % reservable.nome.encode("utf-8")
            email_text = '''
                Olá, %s,
                Sua reserva de %s para o dia %s%s, das %s às %s, está aguardando aprovação. Você receberá uma notificação quando o estado da sua reserva for atualizado.

                -------
                E-mail automático, por favor não responda.
            ''' % (user, reservable.nome.encode("utf-8"), date.strftime('%d/%m/%Y'), recurrent_text, start.strftime('%H:%M'), end.strftime('%H:%M'))
        elif status == 'D':
            email_title = 'Reserva de %s negada.' % reservable.nome.encode("utf-8")
            email_text = '''
                Olá, %s,
                Sua reserva de %s para o dia %s%s, das %s às %s, foi negada.

                -------
                E-mail automático, por favor não responda.
            ''' % (user, reservable.nome.encode("utf-8"), date.strftime('%d/%m/%Y'), recurrent_text, start.strftime('%H:%M'), end.strftime('%H:%M'))
        try:
            send_mail(email_title, email_text, settings.EMAIL_HOST_USER, [user.email])
        except:
            messages.error(self.request, 'E-mail não enviado para solicitante.')

        # If the user doesn't have permission we need to send a e-mail to the reservable responsable
        if status == 'E':
            # Need to check reservable instance to genereate the link
            if isinstance(reservable, EspacoFisico):
                reserve_type = 'reservaespacofisico'
            elif isinstance(reservable, Equipamento):
                reserve_type = 'reservaequipamento'

            base_url = self.request.build_absolute_uri('/')
            url = "%sadmin/agenda/%s/%d/change/" % (base_url, reserve_type, instance.id)

            for responsable in responsables:
                email_title = 'Pedido de reserva de %s' % reservable.nome.encode("utf-8")
                email_text = '''
                    Olá, %s,
                    %s fez um pedido de reserva em %s, para o dia %s%s, das %s às %s. Use o link abaixo para analisar o pedido.
                    %s

                    -------
                    E-mail automático, por favor não responda.
                ''' % (responsable, user, reservable.nome.encode("utf-8"), date.strftime('%d/%m/%Y'), recurrent_text, start.strftime('%H:%M'), end.strftime('%H:%M'), url)
                try:
                    send_mail(email_title, email_text, settings.EMAIL_HOST_USER, [responsable.email])
                except:
                    messages.error(self.request, 'E-mail não enviado para responsável')

    def clean(self):
        cleaned_data = super(ReservaAdminForm, self).clean()
        recurrent = cleaned_data['recorrente']
        if recurrent and self.is_valid():
            # check if starting and ending date was selected
            errors = dict()
            if (not cleaned_data['dataInicio']) and (not self.is_new_object):
                errors['dataInicio'] = 'Este campo é obrigatório.'
            if not cleaned_data['dataFim']:
                errors['dataFim'] = 'Este campo é obrigatório.'
            if bool(errors):
                raise ValidationError(errors)

            # check if ending date is bigger than starting
            if (self.is_new_object) and (cleaned_data['dataFim'] < cleaned_data['data']):
                raise ValidationError({'dataFim': 'Data final deve ser maior que a inicial.'})

            # If fisical aspects of the reserve have been changed we need to check for conflict, otherwise not
            check_conflict = False
            dont_check_field = ['estado', 'atividade', 'ramal', 'finalidade', 'usuario', 'recorrente', 'dataInicio', 'dataFim']
            # Check form variables
            for key in cleaned_data:
                if (key in self.changed_data) and (key not in dont_check_field):
                    check_conflict = True
            # Check recurrent object variables
            recurrent_object = self.instance.recorrencia
            if not self.is_new_object:
                if (cleaned_data['dataInicio'] != recurrent_object.dataInicio) or (cleaned_data['dataFim'] != recurrent_object.dataFim):
                    check_conflict = True

            # check if there isn't datetime conflict in the selected timespan
            if check_conflict:
                error = self.recurrent_option_possible(cleaned_data)
                if error:
                    raise ValidationError({'dataFim': error})

        return cleaned_data

    # Maybe this function has to be in the model, but that wouldn't allow correct error feedback for the user
    def recurrent_option_possible(self,cleaned_data):
        # get necessary variables
        reservable = cleaned_data['locavel']
        starting_date = cleaned_data['data']
        ending_date = cleaned_data['dataFim']
        starting_time = cleaned_data['horaInicio']
        ending_time = cleaned_data['horaFim']
        dummy_activitie = Atividade.objects.create(nome='dummy', descricao='dummy')

        # Don't need to check self reserves in case of an update
        try:
            query = self.instance.recorrencia.get_reserves()
        except:
            query = self.reserve_type.objects.none()

        # Test max advance reserve
        advance = (ending_date - datetime.now().date()).days
        if reservable.antecedenciaMaxima != 0:
            if advance > reservable.antecedenciaMaxima:
                return ('Este locável tem antecedência máxima de %d dias.' % (reservable.antecedenciaMaxima, ))

        # test if there's no conflict
        current_date = starting_date
        error = ''
        while current_date <= ending_date:
            dummy_reserve = self.reserve_type.objects.create(data=current_date, horaInicio=starting_time, horaFim=ending_time, atividade=dummy_activitie, usuario=self.request.user, ramal=1, finalidade='1', locavel=reservable)
            error = dict()
            dummy_reserve.verificaChoque(error, query)
            dummy_reserve.delete()
            if bool(error):
                error =  'Reservas nesse período causarão choque de horário.'
            current_date = current_date + timedelta(days=7)

        dummy_activitie.delete()
        return error

    def save(self, *args, **kwargs):
        user_query = kwargs.pop('query', None)
        reservable = self.cleaned_data['locavel']
        status = self.cleaned_data['estado']

        instance = super(ReservaAdminForm, self).save(commit=False)
        # Check if the user has permission in this reservable
        # If it is, the reserve is automatically accepted
        if reservable in user_query:
            status = 'A'
        instance.estado = status

        instance.save()
        # Treat recurrent reserves
        if self.cleaned_data['recorrente']:
            if self.is_new_object:
                self.create_recurrent_reserve(instance)
            else:
                self.update_recurrent_reserves(instance)

        self.send_mail(status, instance)

        return instance

    def update_recurrent_reserves(self, instance):
        # Look for the recurrent reserve that matches the current reserve
        current_reserve_chain = instance.recorrencia

        # Get queryset
        reserve_query = current_reserve_chain.get_reserves()

        # Change it's fields to match the new version, except for the data
        for reserve in reserve_query:
            today = datetime.now().date()
            if reserve.data >= today:
                for key in reserve.__dict__:
                    if key != 'data':
                        setattr(reserve, key, getattr(instance, key))
                        reserve.save()
        current_reserve_chain.update_fields(instance.data)


    def create_recurrent_reserve(self, instance):
        # If reserve is recurrent, create all reserves
        # Get all necessary variables
        date = self.cleaned_data['data']
        starting_date = date
        ending_date = self.cleaned_data['dataFim']
        starting_time = self.cleaned_data['horaInicio']
        ending_date = self.cleaned_data['dataFim']
        ending_time = self.cleaned_data['horaFim']
        activity = self.cleaned_data['atividade']
        user = self.cleaned_data['usuario']
        ramal = self.cleaned_data['ramal']
        reason = self.cleaned_data['finalidade']
        reservable = self.cleaned_data['locavel']
        recurrent_chain = ReservaRecorrente.objects.create(dataInicio=date, dataFim=ending_date)  # create the recurrent object that will chain the reserves
        recurrent_chain.save()

        # Create reserves
        instance.recorrencia = recurrent_chain  # add the recurrent_chain to the original reserve
        current_date = date + timedelta(days=7) # the starting will aready be created by the form
        while current_date <= ending_date:
            recurrent_reserve = self.reserve_type.objects.create(estado=instance.estado, data=current_date, recorrencia=recurrent_chain, horaInicio=starting_time, horaFim=ending_time, atividade=activity, usuario=user, ramal=ramal, finalidade=reason, locavel=reservable)
            recurrent_reserve.save()
            current_date = current_date + timedelta(days=7)
        instance.save()


class ReservaEquipamentoAdminForm(ReservaAdminForm):
    class Meta:
        model = ReservaEquipamento
        fields = ('estado', 'data', 'recorrente', 'dataInicio', 'dataFim', 'horaInicio', 'horaFim', 'locavel', 'atividade', 'usuario', 'ramal', 'finalidade')
    def __init__(self, *args, **kwargs):
        kwargs['admin_type'] = admin.EquipamentoAdmin
        kwargs['reservable_type'] = Equipamento
        kwargs['reserve_type'] = ReservaEquipamento
        super(ReservaEquipamentoAdminForm, self).__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        temp_request = self.request
        temp_request.user = self.cleaned_data['usuario']
        ma = admin.EquipamentoAdmin(Equipamento, AdminSite())
        user_query = ma.get_queryset(temp_request)
        kwargs['query'] = user_query
        return super(ReservaEquipamentoAdminForm, self).save(*args, **kwargs)

class ReservaEspacoFisicoAdminForm(ReservaAdminForm):
    class Meta:
        model = ReservaEspacoFisico
        fields = ('estado', 'data', 'recorrente', 'dataInicio', 'dataFim', 'horaInicio', 'horaFim', 'locavel', 'atividade', 'usuario', 'ramal', 'finalidade')
    def __init__(self, *args, **kwargs):
        kwargs['admin_type'] = admin.EspacoFisicoAdmin
        kwargs['reservable_type'] = EspacoFisico
        kwargs['reserve_type'] = ReservaEspacoFisico
        super(ReservaEspacoFisicoAdminForm, self).__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        temp_request = self.request
        temp_request.user = self.cleaned_data['usuario']
        ma = admin.EspacoFisicoAdmin(EspacoFisico, AdminSite())
        user_query = ma.get_queryset(self.request)
        kwargs['query'] = user_query
        return super(ReservaEspacoFisicoAdminForm, self).save(*args, **kwargs)

class UnidadeAdminForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super(UnidadeAdminForm, self).__init__(*args, **kwargs)
        # get queryset from admin
        ma = admin.UnidadeAdmin(Unidade, AdminSite())
        queryset = ma.get_queryset(self.request)
        # set possible options on the field
        self.fields['unidadePai'].queryset = queryset

        # get the old responsables for future comparissons
        try:
            self.initial_responsables = kwargs['instance'].responsavel
        # if it's a new form there's no old responsables
        except:
            self.initial_responsables = User.objects.none()

        self.init_labels()
        self.remove_add_and_edit_icons()

    def remove_add_and_edit_icons(self):
        self.fields['unidadePai'].widget.can_add_related = False  # remove add button
        self.fields['unidadePai'].widget.can_change_related = False  # remove edit button
        self.fields['responsavel'].widget.can_add_related = False  # remove add button
        self.fields['grupos'].widget.can_add_related = False  # remove add button

    def init_labels(self):
        self.fields['unidadePai'].label = 'Unidade pai'
        self.fields['responsavel'].label = 'Responsáveis'
        self.fields['descricao'].label = 'Descrição '
        self.fields['logoLink'].label = 'Link para a logo'

    def save(self, *args, **kwargs):
        new_responsables = self.cleaned_data['responsavel']
        instance = super(UnidadeAdminForm, self).save(commit=False)
        instance.save()

        group = Group.objects.get_or_create(name='responsables')[0]
        # Add new responsables to group
        for user in new_responsables:
            user.is_staff = True
            user.save()
            group.user_set.add(user)

        for old_responsable in self.initial_responsables.all():
            # Check if user removed from responsable.
            if old_responsable not in new_responsables.all():
                # check if it has other permissions, aside for the one being remove. if not remove from group
                user_responsabilities = bool(old_responsable.unidade_set.exclude(id=instance.id))
                user_responsabilities = user_responsabilities or bool(old_responsable.espacofisico_set.all())
                user_responsabilities = user_responsabilities or bool(old_responsable.equipamento_set.all())
                if not user_responsabilities:
                    group.user_set.remove(old_responsable)
                    old_responsable.is_staff = False
                    old_responsable.save()
        return instance

    def clean(self):
        cleaned_data = super(UnidadeAdminForm, self).clean()
        father_unit = cleaned_data['unidadePai']
        if father_unit==None and not self.request.user.is_superuser:
            raise ValidationError({'unidadePai': "Escolha uma unidade pai."})
        return cleaned_data

class SearchFilterForm(forms.Form):
    def __init__(self, *args, **kwargs):
        try:
            self.tipo_init = kwargs.pop('tipo')
            super(SearchFilterForm,self).__init__(*args,**kwargs)
            self.fields['tipo'].initial = self.tipo_init
        except:
            super(SearchFilterForm,self).__init__(*args,**kwargs)

    data = forms.DateField(input_formats=['%d/%m/%Y'], widget=SelectDateWidget())
    data.label = ''
    horaInicio = forms.TimeField(input_formats=['%H:%M'], widget=SelectTimeWidget())
    horaInicio.label = ''
    horaFim = forms.TimeField(input_formats=['%H:%M'], widget=SelectTimeWidget())
    horaFim.label = ''
    tipo = forms.CharField(widget = forms.HiddenInput())

    def clean(self):
        cleaned_data = super(SearchFilterForm, self).clean()

class LocavelAdminForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        self.reservable_type = kwargs.pop('reservable_type')
        super(LocavelAdminForm, self).__init__(*args, **kwargs)
        self.fields['antecedenciaMinima'].initial = 0
        self.fields['antecedenciaMaxima'].initial = 0
        self.init_labels()
        self.remove_add_and_edit_icons()
        ma = admin.UnidadeAdmin(Unidade, AdminSite())
        queryset = ma.get_queryset(self.request)
        self.fields['unidade'].queryset = queryset
        # get the old responsables for future comparissons
        try:
            self.initial_responsables = kwargs['instance'].responsavel
        # if it's a new form there's no old responsables
        except:
            self.initial_responsables = User.objects.none()

    def remove_add_and_edit_icons(self):
        self.fields['responsavel'].widget.can_add_related = False  # remove add button
        self.fields['responsavel'].widget.can_change_related = False  # remove edit button
        self.fields['unidade'].widget.can_add_related = False  # remove add button
        self.fields['unidade'].widget.can_change_related = False  # remove edit button
        self.fields['atividadesPermitidas'].widget.can_add_related = False  # remove add button
        self.fields['atividadesPermitidas'].widget.can_change_related = False  # remove edit button
        self.fields['grupos'].widget.can_add_related = False  # remove add button

    def init_labels(self):
        self.fields['antecedenciaMinima'].label = 'Antecedência mínima para reserva. (Em dias, 0 para sem antecedencia)'
        self.fields['antecedenciaMaxima'].label = 'Antecedência máxima para reserva. (Em dias, 0 para sem antecedencia)'
        self.fields['fotoLink'].label = 'Link para foto'
        self.fields['atividadesPermitidas'].label = 'Atividades permitidas'
        self.fields['descricao'].label = 'Descrição'
        self.fields['responsavel'].label = 'Responsáveis'
        self.fields['invisivel'].label = 'Invisível'
        self.fields['localizacao'].label = 'Localização'

    def save(self, *args, **kwargs):
        new_responsables = self.cleaned_data['responsavel']
        instance = super(LocavelAdminForm, self).save(commit=False)
        instance.save()

        group = Group.objects.get_or_create(name='responsables')[0]
        # Add new responsables to group
        for user in new_responsables:
            user.is_staff = True
            user.save()
            group.user_set.add(user)

        for old_responsable in self.initial_responsables.all():
            # Check if user removed from responsable.
            if old_responsable not in new_responsables.all():
                # check if it has other permissions, aside for the one being remove. if not remove from group
                user_responsabilities = bool(old_responsable.unidade_set.all())
                if self.reservable_type == Equipamento:
                    user_responsabilities = user_responsabilities or bool(old_responsable.espacofisico_set.all())
                    user_responsabilities = user_responsabilities or bool(old_responsable.equipamento_set.exclude(id=instance.id))
                elif self.reservable_type == EspacoFisico:
                    user_responsabilities = user_responsabilities or bool(old_responsable.equipamento_set.all())
                    user_responsabilities = user_responsabilities or bool(old_responsable.espacofisico_set.exclude(id=instance.id))
                if not user_responsabilities:
                    group.user_set.remove(old_responsable)
                    old_responsable.is_staff = False
                    old_responsable.save()
        return instance


class EquipamentoAdminForm(LocavelAdminForm):

    def __init__(self, *args, **kwargs):
        kwargs['reservable_type'] = Equipamento
        super(EquipamentoAdminForm, self).__init__(*args, **kwargs)
        self.fields['patrimonio'].label = 'Patrimônio'

    def save(self, *args, **kwargs):
        return super(EquipamentoAdminForm, self).save(*args, **kwargs)

class EspacoFisicoAdminForm(LocavelAdminForm):

    def __init__(self, *args, **kwargs):
        kwargs['reservable_type'] = EspacoFisico
        super(EspacoFisicoAdminForm, self).__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        return super(EspacoFisicoAdminForm, self).save(*args, **kwargs)