from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count, Sum

from .models import Verwaltung, Standort, WanLeitung, Vertrag
from .forms import (
    StandortForm,
    VerwaltungForm,
    VertragForm,
    WanLeitungForm,
)


def user_in_group(user, group_name: str) -> bool:
    return user.is_authenticated and user.groups.filter(name=group_name).exists()


def is_super_or_net_admin(user) -> bool:
    # Superuser immer dürfen, plus Gruppen SUPERADMIN & NETZADMIN
    return (
        user.is_superuser
        or user_in_group(user, "SUPERADMIN")
        or user_in_group(user, "NETZADMIN")
    )


@login_required
def dashboard(request):
    user = request.user

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        verwaltungen = Verwaltung.objects.filter(id=user.profile.verwaltung.id)
    else:
        verwaltungen = Verwaltung.objects.all()

    verwaltungen = verwaltungen.annotate(
        standort_count=Count("standorte", distinct=True),
        leitung_count=Count("standorte__leitungen", distinct=True),
        kosten_monat=Sum("vertraege__kosten_monat_netto"),
    )

    context = {
        "verwaltungen": verwaltungen,
    }
    return render(request, "core/dashboard.html", context)


@login_required
def verwaltung_list(request):
    user = request.user

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        verwaltungen = Verwaltung.objects.filter(id=user.profile.verwaltung.id)
    else:
        verwaltungen = Verwaltung.objects.all()

    verwaltungen = verwaltungen.annotate(
        standort_count=Count("standorte", distinct=True),
        leitung_count=Count("standorte__leitungen", distinct=True),
    )

    context = {
        "verwaltungen": verwaltungen,
        "can_create_verwaltung": is_super_or_net_admin(user),
    }
    return render(request, "core/verwaltung_list.html", context)


@login_required
@user_passes_test(is_super_or_net_admin)
def verwaltung_create(request):
    if request.method == "POST":
        form = VerwaltungForm(request.POST)
        if form.is_valid():
            verwaltung = form.save()
            return redirect("core:verwaltung_detail", pk=verwaltung.pk)
    else:
        form = VerwaltungForm()

    context = {
        "form": form,
    }
    return render(request, "core/verwaltung_form.html", context)


@login_required
@user_passes_test(is_super_or_net_admin)
def verwaltung_update(request, pk):
    verwaltung = get_object_or_404(Verwaltung, pk=pk)

    if request.method == "POST":
        form = VerwaltungForm(request.POST, instance=verwaltung)
        if form.is_valid():
            verwaltung = form.save()
            return redirect("core:verwaltung_detail", pk=verwaltung.pk)
    else:
        form = VerwaltungForm(instance=verwaltung)

    context = {
        "form": form,
        "is_edit": True,
        "verwaltung": verwaltung,
    }
    return render(request, "core/verwaltung_form.html", context)


@login_required
def verwaltung_detail(request, pk):
    user = request.user
    verwaltung = get_object_or_404(Verwaltung, pk=pk)

    # IT-Beauftragter darf nur seine eigene Verwaltung sehen
    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        if verwaltung.id != user.profile.verwaltung_id:
            return render(request, "core/forbidden.html", status=403)

    standorte = (
        verwaltung.standorte
        .select_related("verwaltung")
        .annotate(leitung_count=Count("leitungen"))
    )

    vertraege = verwaltung.vertraege.all()

    leitungen = (
        WanLeitung.objects
        .select_related("standort", "standort__verwaltung", "vertrag")
        .filter(standort__verwaltung=verwaltung)
    )

    context = {
        "verwaltung": verwaltung,
        "standorte": standorte,
        "vertraege": vertraege,
        "leitungen": leitungen,
        "can_edit": is_super_or_net_admin(user),
    }
    return render(request, "core/verwaltung_detail.html", context)


@login_required
def standort_list(request):
    user = request.user

    standorte = Standort.objects.select_related("verwaltung").annotate(
        leitung_count=Count("leitungen")
    )

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        standorte = standorte.filter(verwaltung=user.profile.verwaltung)

    search = request.GET.get("q")
    if search:
        standorte = standorte.filter(name__icontains=search)

    context = {
        "standorte": standorte,
        "search": search,
        "can_create_standort": is_super_or_net_admin(user),
    }
    return render(request, "core/standort_list.html", context)


@login_required
@user_passes_test(is_super_or_net_admin)
def standort_create(request):
    if request.method == "POST":
        form = StandortForm(request.POST)
        if form.is_valid():
            standort = form.save()
            return redirect("core:standort_detail", pk=standort.pk)
    else:
        form = StandortForm()

    context = {
        "form": form,
    }
    return render(request, "core/standort_form.html", context)


@login_required
@user_passes_test(is_super_or_net_admin)
def standort_update(request, pk):
    standort = get_object_or_404(Standort, pk=pk)

    if request.method == "POST":
        form = StandortForm(request.POST, instance=standort)
        if form.is_valid():
            standort = form.save()
            return redirect("core:standort_detail", pk=standort.pk)
    else:
        form = StandortForm(instance=standort)

    context = {
        "form": form,
        "is_edit": True,
        "standort": standort,
    }
    return render(request, "core/standort_form.html", context)


@login_required
def standort_detail(request, pk):
    user = request.user
    standort = get_object_or_404(Standort.objects.select_related("verwaltung"), pk=pk)

    # Zugriffsbeschränkung: IT-Beauftragter darf nur eigene Verwaltung
    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        if standort.verwaltung_id != user.profile.verwaltung_id:
            return render(request, "core/forbidden.html", status=403)

    leitungen = standort.leitungen.select_related("vertrag")

    context = {
        "standort": standort,
        "leitungen": leitungen,
        "can_edit": is_super_or_net_admin(user),
    }
    return render(request, "core/standort_detail.html", context)


@login_required
def wanleitung_list(request):
    user = request.user

    leitungen = WanLeitung.objects.select_related(
        "standort", "standort__verwaltung", "vertrag"
    )

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        leitungen = leitungen.filter(standort__verwaltung=user.profile.verwaltung)

    context = {
        "leitungen": leitungen,
        "can_create_wanleitung": is_super_or_net_admin(user),
    }
    return render(request, "core/wanleitung_list.html", context)


@login_required
@user_passes_test(is_super_or_net_admin)
def wanleitung_create(request):
    if request.method == "POST":
        form = WanLeitungForm(request.POST)
        if form.is_valid():
            leitung = form.save()
            return redirect("core:wanleitung_detail", pk=leitung.pk)
    else:
        form = WanLeitungForm()

    context = {
        "form": form,
    }
    return render(request, "core/wanleitung_form.html", context)


@login_required
@user_passes_test(is_super_or_net_admin)
def wanleitung_update(request, pk):
    leitung = get_object_or_404(WanLeitung, pk=pk)

    if request.method == "POST":
        form = WanLeitungForm(request.POST, instance=leitung)
        if form.is_valid():
            leitung = form.save()
            return redirect("core:wanleitung_detail", pk=leitung.pk)
    else:
        form = WanLeitungForm(instance=leitung)

    context = {
        "form": form,
        "is_edit": True,
        "leitung": leitung,
    }
    return render(request, "core/wanleitung_form.html", context)


@login_required
def wanleitung_detail(request, pk):
    leitung = get_object_or_404(
        WanLeitung.objects.select_related("standort", "standort__verwaltung", "vertrag"),
        pk=pk,
    )
    user = request.user

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        if leitung.standort.verwaltung_id != user.profile.verwaltung_id:
            return render(request, "core/forbidden.html", status=403)

    context = {
        "leitung": leitung,
        "can_edit": is_super_or_net_admin(user),
    }
    return render(request, "core/wanleitung_detail.html", context)


@login_required
def vertrag_list(request):
    user = request.user

    vertraege = Vertrag.objects.select_related("verwaltung")

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        vertraege = vertraege.filter(verwaltung=user.profile.verwaltung)

    context = {
        "vertraege": vertraege,
        "can_create_vertrag": is_super_or_net_admin(user),
    }
    return render(request, "core/vertrag_list.html", context)


@login_required
@user_passes_test(is_super_or_net_admin)
def vertrag_create(request):
    if request.method == "POST":
        form = VertragForm(request.POST)
        if form.is_valid():
            vertrag = form.save()
            return redirect("core:vertrag_detail", pk=vertrag.pk)
    else:
        form = VertragForm()

    context = {
        "form": form,
    }
    return render(request, "core/vertrag_form.html", context)


@login_required
@user_passes_test(is_super_or_net_admin)
def vertrag_update(request, pk):
    vertrag = get_object_or_404(Vertrag, pk=pk)

    if request.method == "POST":
        form = VertragForm(request.POST, instance=vertrag)
        if form.is_valid():
            vertrag = form.save()
            return redirect("core:vertrag_detail", pk=vertrag.pk)
    else:
        form = VertragForm(instance=vertrag)

    context = {
        "form": form,
        "is_edit": True,
        "vertrag": vertrag,
    }
    return render(request, "core/vertrag_form.html", context)


@login_required
def vertrag_detail(request, pk):
    vertrag = get_object_or_404(Vertrag.objects.select_related("verwaltung"), pk=pk)
    user = request.user

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        if vertrag.verwaltung_id != user.profile.verwaltung_id:
            return render(request, "core/forbidden.html", status=403)

    leitungen = vertrag.leitungen.select_related("standort", "standort__verwaltung")

    context = {
        "vertrag": vertrag,
        "leitungen": leitungen,
        "can_edit": is_super_or_net_admin(user),
    }
    return render(request, "core/vertrag_detail.html", context)
