from decimal import Decimal

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect

from django.db.models import (
    Count,
    Sum,
    OuterRef,
    Subquery,
    IntegerField,
    DecimalField,
    Value,
    Prefetch,  # ← EINZIGE NEUE SACHE
)
from django.db.models.functions import Coalesce

from .models import Verwaltung, Standort, WanLeitung, Vertrag, Provider, Tarif
from .forms import (
    StandortForm,
    VerwaltungForm,
    VertragForm,
    WanLeitungForm,
    ProviderForm,
    TarifForm,
)


def user_in_group(user, group_name: str) -> bool:
    return user.is_authenticated and user.groups.filter(name=group_name).exists()


def is_super_or_net_admin(user) -> bool:
    return (
        user.is_superuser
        or user_in_group(user, "SUPERADMIN")
        or user_in_group(user, "NETZADMIN")
    )


def _verwaltungen_queryset_for_user(user):
    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        return Verwaltung.objects.filter(id=user.profile.verwaltung.id)
    return Verwaltung.objects.all()


def _annotate_verwaltung_counts_and_sums(qs):
    """
    Annotates für:
      - standort_count
      - leitung_count
      - kosten_monat
      - arbeitsplaetze_sum
    """

    standort_sum_subq = (
        Standort.objects
        .filter(verwaltung=OuterRef("pk"))
        .values("verwaltung")
        .annotate(s=Sum("arbeitsplaetze"))
        .values("s")[:1]
    )

    kosten_sum_subq = (
        Vertrag.objects
        .filter(verwaltung=OuterRef("pk"))
        .values("verwaltung")
        .annotate(s=Sum("kosten_monat_netto"))
        .values("s")[:1]
    )

    return qs.annotate(
        standort_count=Count("standorte", distinct=True),
        leitung_count=Count("standorte__leitungen", distinct=True),

        arbeitsplaetze_sum=Coalesce(
            Subquery(standort_sum_subq, output_field=IntegerField()),
            Value(0),
            output_field=IntegerField(),
        ),

        kosten_monat=Coalesce(
            Subquery(
                kosten_sum_subq,
                output_field=DecimalField(max_digits=10, decimal_places=2),
            ),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
    )


# ---------------------------- Dashboard ----------------------------

@login_required
def dashboard(request):
    user = request.user
    verwaltungen = _verwaltungen_queryset_for_user(user)
    verwaltungen = _annotate_verwaltung_counts_and_sums(verwaltungen)

    return render(request, "core/dashboard.html", {"verwaltungen": verwaltungen})


# ---------------------------- Verwaltungen ----------------------------

@login_required
def verwaltung_list(request):
    user = request.user
    verwaltungen = _verwaltungen_queryset_for_user(user)
    verwaltungen = _annotate_verwaltung_counts_and_sums(verwaltungen)

    return render(
        request,
        "core/verwaltung_list.html",
        {
            "verwaltungen": verwaltungen,
            "can_create_verwaltung": is_super_or_net_admin(user),
        },
    )


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

    return render(request, "core/verwaltung_form.html", {"form": form})


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

    return render(
        request,
        "core/verwaltung_form.html",
        {"form": form, "is_edit": True, "verwaltung": verwaltung},
    )


@login_required
def verwaltung_detail(request, pk):
    user = request.user
    verwaltung = get_object_or_404(Verwaltung, pk=pk)

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        if verwaltung.id != user.profile.verwaltung_id:
            return render(request, "core/forbidden.html", status=403)

    standorte = (
        verwaltung.standorte
        .select_related("verwaltung")
        .annotate(leitung_count=Count("leitungen"))
    )

    arbeitsplaetze_sum = standorte.aggregate(s=Sum("arbeitsplaetze"))["s"] or 0

    vertraege = verwaltung.vertraege.all()

    leitungen = (
        WanLeitung.objects
        .select_related("standort", "standort__verwaltung", "vertrag")
        .filter(standort__verwaltung=verwaltung)
    )

    return render(
        request,
        "core/verwaltung_detail.html",
        {
            "verwaltung": verwaltung,
            "standorte": standorte,
            "vertraege": vertraege,
            "leitungen": leitungen,
            "arbeitsplaetze_sum": arbeitsplaetze_sum,
            "can_edit": is_super_or_net_admin(user),
        },
    )


# ---------------------------- Standorte ----------------------------

@login_required
def standort_list(request):
    user = request.user

    leitungen_qs = WanLeitung.objects.select_related(
        "provider_ref",
        "tarif_ref",
        "vertrag",
    )

    standorte = (
        Standort.objects
        .select_related("verwaltung")
        .prefetch_related(
            Prefetch("leitungen", queryset=leitungen_qs)
        )
        .annotate(leitung_count=Count("leitungen"))
    )

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        standorte = standorte.filter(verwaltung=user.profile.verwaltung)

    search = request.GET.get("q")
    if search:
        standorte = standorte.filter(name__icontains=search)

    return render(
        request,
        "core/standort_list.html",
        {
            "standorte": standorte,
            "search": search,
            "can_create_standort": is_super_or_net_admin(user),
        },
    )


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

    return render(request, "core/standort_form.html", {"form": form})


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

    return render(
        request,
        "core/standort_form.html",
        {"form": form, "is_edit": True, "standort": standort},
    )


@login_required
def standort_detail(request, pk):
    user = request.user
    standort = get_object_or_404(Standort.objects.select_related("verwaltung"), pk=pk)

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        if standort.verwaltung_id != user.profile.verwaltung_id:
            return render(request, "core/forbidden.html", status=403)

    leitungen = standort.leitungen.select_related(
        "vertrag",
        "provider_ref",
        "tarif_ref",
    )

    return render(
        request,
        "core/standort_detail.html",
        {
            "standort": standort,
            "leitungen": leitungen,
            "can_edit": is_super_or_net_admin(user),
        },
    )


# ---------------------------- WAN-Leitungen ----------------------------

@login_required
def wanleitung_list(request):
    user = request.user

    leitungen = WanLeitung.objects.select_related(
        "standort",
        "standort__verwaltung",
        "vertrag",
        "provider_ref",
        "tarif_ref",
    )

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        leitungen = leitungen.filter(standort__verwaltung=user.profile.verwaltung)

    return render(
        request,
        "core/wanleitung_list.html",
        {
            "leitungen": leitungen,
            "can_create_wanleitung": is_super_or_net_admin(user),
        },
    )


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

    return render(request, "core/wanleitung_form.html", {"form": form})


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

    return render(
        request,
        "core/wanleitung_form.html",
        {"form": form, "is_edit": True, "leitung": leitung},
    )


@login_required
def wanleitung_detail(request, pk):
    leitung = get_object_or_404(
        WanLeitung.objects.select_related(
            "standort",
            "standort__verwaltung",
            "vertrag",
            "provider_ref",
            "tarif_ref",
        ),
        pk=pk,
    )
    user = request.user

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        if leitung.standort.verwaltung_id != user.profile.verwaltung_id:
            return render(request, "core/forbidden.html", status=403)

    return render(
        request,
        "core/wanleitung_detail.html",
        {
            "leitung": leitung,
            "can_edit": is_super_or_net_admin(user),
        },
    )


# ---------------------------- Verträge ----------------------------

@login_required
def vertrag_list(request):
    user = request.user

    vertraege = Vertrag.objects.select_related("verwaltung", "provider_ref")

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        vertraege = vertraege.filter(verwaltung=user.profile.verwaltung)

    return render(
        request,
        "core/vertrag_list.html",
        {
            "vertraege": vertraege,
            "can_create_vertrag": is_super_or_net_admin(user),
        },
    )


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

    return render(request, "core/vertrag_form.html", {"form": form})


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

    return render(
        request,
        "core/vertrag_form.html",
        {"form": form, "is_edit": True, "vertrag": vertrag},
    )


@login_required
def vertrag_detail(request, pk):
    vertrag = get_object_or_404(
        Vertrag.objects.select_related("verwaltung", "provider_ref"),
        pk=pk,
    )
    user = request.user

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        if vertrag.verwaltung_id != user.profile.verwaltung_id:
            return render(request, "core/forbidden.html", status=403)

    leitungen = vertrag.leitungen.select_related(
        "standort",
        "standort__verwaltung",
        "provider_ref",
        "tarif_ref",
    )

    return render(
        request,
        "core/vertrag_detail.html",
        {
            "vertrag": vertrag,
            "leitungen": leitungen,
            "can_edit": is_super_or_net_admin(user),
        },
    )
