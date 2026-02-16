from decimal import Decimal
from urllib.parse import quote

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect

from django.db.models import (
    Count,
    Sum,
    Q,
    OuterRef,
    Subquery,
    IntegerField,
    DecimalField,
    Value,
    Prefetch,
)
from django.db.models.functions import Coalesce

from .models import (
    Verwaltung,
    Standort,
    WanLeitung,
    WanBeauftragung,
    WanBeauftragungProviderKontext,
    Vertrag,
    Provider,
    ProviderZusatzoption,
    Tarif,
)
from .forms import (
    StandortForm,
    VerwaltungForm,
    VertragForm,
    WanLeitungForm,
    WanBeauftragungForm,
    WanBeauftragungProviderKontextForm,
    ProviderForm,
    ProviderZusatzoptionForm,
    TarifForm,
)

# --- WAN Config (MBits pro Arbeitsplatz, Down + Up) ---
try:
    from .wan_config import (
        WAN_MBIT_PER_AP_DOWN,
        WAN_MBIT_PER_AP_UP,
        WAN_THRESHOLD_GREEN,
        WAN_THRESHOLD_YELLOW,
    )
except Exception:
    WAN_MBIT_PER_AP_DOWN = 10
    WAN_MBIT_PER_AP_UP = 2
    WAN_THRESHOLD_GREEN = 1.30
    WAN_THRESHOLD_YELLOW = 0.90


def user_in_group(user, group_name: str) -> bool:
    return user.is_authenticated and user.groups.filter(name=group_name).exists()


def is_super_or_net_admin(user) -> bool:
    return (
        user.is_superuser
        or user_in_group(user, "SUPERADMIN")
        or user_in_group(user, "NETZADMIN")
    )


def can_manage_beauftragung(user) -> bool:
    return (
        is_super_or_net_admin(user)
        or user_in_group(user, "IT-BEAUFTRAGTER")
        or user_in_group(user, "EINKAEUFER")
        or user_in_group(user, "EINKAUFER")
    )


def _verwaltungen_queryset_for_user(user):
    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        return Verwaltung.objects.filter(id=user.profile.verwaltung.id)
    return Verwaltung.objects.all()


def _sync_provider_kontexte(beauftragung):
    provider_ids = set(beauftragung.angefragte_provider.values_list("id", flat=True))
    existing = {
        k.provider_id: k
        for k in WanBeauftragungProviderKontext.objects.filter(beauftragung=beauftragung)
    }

    for provider_id in provider_ids - set(existing.keys()):
        WanBeauftragungProviderKontext.objects.create(
            beauftragung=beauftragung,
            provider_id=provider_id,
        )

    WanBeauftragungProviderKontext.objects.filter(
        beauftragung=beauftragung
    ).exclude(provider_id__in=provider_ids).delete()


def _annotate_verwaltung_counts_and_sums(qs):
    """
    Annotates für:
      - standort_count
      - leitung_count
      - kosten_monat (Summe der Verträge)
      - arbeitsplaetze_sum (Summe der Standorte)

    Summen per Subquery, damit JOINs nichts multiplizieren.
    """

    # Summe Arbeitsplätze pro Verwaltung (Integer)
    standort_sum_subq = (
        Standort.objects
        .filter(verwaltung=OuterRef("pk"))
        .values("verwaltung")
        .annotate(s=Sum("arbeitsplaetze"))
        .values("s")[:1]
    )

    # Summe Kosten pro Verwaltung (Decimal)
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
            Subquery(kosten_sum_subq, output_field=DecimalField(max_digits=10, decimal_places=2)),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
    )


# ---------------------------- Dashboard ----------------------------

@login_required
def dashboard(request):
    user = request.user
    verwaltungen = _verwaltungen_queryset_for_user(user)
    verwaltungen = _annotate_verwaltung_counts_and_sums(verwaltungen).order_by("kuerzel")

    return render(request, "core/dashboard.html", {"verwaltungen": verwaltungen})


# ---------------------------- Verwaltungen ----------------------------

@login_required
def verwaltung_list(request):
    user = request.user
    verwaltungen = _verwaltungen_queryset_for_user(user)
    verwaltungen = _annotate_verwaltung_counts_and_sums(verwaltungen).order_by("kuerzel")

    return render(
        request,
        "core/verwaltung_list.html",
        {"verwaltungen": verwaltungen, "can_create_verwaltung": is_super_or_net_admin(user)},
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

    context = {
        "verwaltung": verwaltung,
        "standorte": standorte,
        "vertraege": vertraege,
        "leitungen": leitungen,
        "arbeitsplaetze_sum": arbeitsplaetze_sum,
        "can_edit": is_super_or_net_admin(user),
    }
    return render(request, "core/verwaltung_detail.html", context)


# ---------------------------- Provider ----------------------------

@login_required
def provider_list(request):
    user = request.user
    providers = Provider.objects.annotate(
        tarif_count=Count("tarife", distinct=True),
        leitung_count=Count("leitungen", distinct=True),
        vertrag_count=Count("vertraege", distinct=True),
    ).order_by("name")

    return render(
        request,
        "core/provider_list.html",
        {"providers": providers, "can_create_provider": is_super_or_net_admin(user)},
    )


@login_required
@user_passes_test(is_super_or_net_admin)
def provider_create(request):
    if request.method == "POST":
        form = ProviderForm(request.POST)
        if form.is_valid():
            provider = form.save()
            return redirect("core:provider_detail", pk=provider.pk)
    else:
        form = ProviderForm()

    return render(request, "core/provider_form.html", {"form": form})


@login_required
@user_passes_test(is_super_or_net_admin)
def provider_update(request, pk):
    provider = get_object_or_404(Provider, pk=pk)

    if request.method == "POST":
        form = ProviderForm(request.POST, instance=provider)
        if form.is_valid():
            provider = form.save()
            return redirect("core:provider_detail", pk=provider.pk)
    else:
        form = ProviderForm(instance=provider)

    return render(
        request,
        "core/provider_form.html",
        {"form": form, "is_edit": True, "provider": provider},
    )


@login_required
def provider_detail(request, pk):
    user = request.user
    provider = get_object_or_404(Provider, pk=pk)

    tarife = provider.tarife.all().order_by("name")
    optionen = provider.zusatzoptionen.all().order_by("name")
    leitungen = provider.leitungen.select_related("standort", "standort__verwaltung", "vertrag")
    vertraege = provider.vertraege.select_related("verwaltung")

    return render(
        request,
        "core/provider_detail.html",
        {
            "provider": provider,
            "tarife": tarife,
            "optionen": optionen,
            "leitungen": leitungen,
            "vertraege": vertraege,
            "can_edit": is_super_or_net_admin(user),
        },
    )


# ---------------------------- Tarife ----------------------------

@login_required
def tarif_list(request):
    user = request.user
    tarife = Tarif.objects.select_related("provider").annotate(
        leitung_count=Count("leitungen", distinct=True),
    ).order_by("provider__name", "name")

    return render(
        request,
        "core/tarif_list.html",
        {"tarife": tarife, "can_create_tarif": is_super_or_net_admin(user)},
    )


@login_required
@user_passes_test(is_super_or_net_admin)
def tarif_create(request):
    provider_id = request.GET.get("provider")
    initial = {"provider": provider_id} if provider_id else None

    if request.method == "POST":
        form = TarifForm(request.POST)
        if form.is_valid():
            tarif = form.save()
            return redirect("core:tarif_detail", pk=tarif.pk)
    else:
        form = TarifForm(initial=initial)

    return render(request, "core/tarif_form.html", {"form": form})


@login_required
@user_passes_test(is_super_or_net_admin)
def tarif_update(request, pk):
    tarif = get_object_or_404(Tarif, pk=pk)

    if request.method == "POST":
        form = TarifForm(request.POST, instance=tarif)
        if form.is_valid():
            tarif = form.save()
            return redirect("core:tarif_detail", pk=tarif.pk)
    else:
        form = TarifForm(instance=tarif)

    return render(
        request,
        "core/tarif_form.html",
        {"form": form, "is_edit": True, "tarif": tarif},
    )


@login_required
def tarif_detail(request, pk):
    user = request.user
    tarif = get_object_or_404(Tarif.objects.select_related("provider"), pk=pk)
    leitungen = tarif.leitungen.select_related("standort", "standort__verwaltung", "vertrag")

    return render(
        request,
        "core/tarif_detail.html",
        {"tarif": tarif, "leitungen": leitungen, "can_edit": is_super_or_net_admin(user)},
    )


# ---------------------------- Standorte ----------------------------

def _status_for(actual, required):
    """
    actual/required -> green/yellow/red/unknown
    """
    if actual is None:
        return "unknown"
    if required <= 0:
        return "green"
    ratio = float(actual) / float(required)
    if ratio >= float(WAN_THRESHOLD_GREEN):
        return "green"
    if ratio >= float(WAN_THRESHOLD_YELLOW):
        return "yellow"
    return "red"


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
        .prefetch_related(Prefetch("leitungen", queryset=leitungen_qs))
        .annotate(leitung_count=Count("leitungen"))
        .order_by("standort_code")   # 🔥 HIER
    )

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        standorte = standorte.filter(verwaltung=user.profile.verwaltung)

    search = request.GET.get("q")
    if search:
        standorte = standorte.filter(name__icontains=search)

    rows = []
    for s in standorte:
        ap = int(getattr(s, "arbeitsplaetze", 0) or 0)
        required_down = ap * int(WAN_MBIT_PER_AP_DOWN)
        required_up = ap * int(WAN_MBIT_PER_AP_UP)

        leitung_items = []
        for l in s.leitungen.all():
            down = getattr(l, "bandbreite_down_mbit", None)
            up = getattr(l, "bandbreite_up_mbit", None)

            leitung_items.append({
                "leitung": l,
                "down": down,
                "up": up,
                "required_down": required_down,
                "required_up": required_up,
                "status_down": _status_for(down, required_down),
                "status_up": _status_for(up, required_up),
            })

        rows.append({
            "standort": s,
            "required_down": required_down,
            "required_up": required_up,
            "leitungen": leitung_items,
        })

    return render(
        request,
        "core/standort_list.html",
        {
            "rows": rows,
            "search": search,
            "can_create_standort": is_super_or_net_admin(user),
            "mbit_per_ap_down": WAN_MBIT_PER_AP_DOWN,
            "mbit_per_ap_up": WAN_MBIT_PER_AP_UP,
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

    leitungen = standort.leitungen.select_related("vertrag", "provider_ref", "tarif_ref")

    return render(
        request,
        "core/standort_detail.html",
        {"standort": standort, "leitungen": leitungen, "can_edit": is_super_or_net_admin(user)},
    )


# ---------------------------- WAN-Leitungen ----------------------------

@login_required
def wanleitung_list(request):
    user = request.user

    leitungen = WanLeitung.objects.select_related(
        "standort", "standort__verwaltung", "vertrag", "provider_ref", "tarif_ref"
    )

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        leitungen = leitungen.filter(standort__verwaltung=user.profile.verwaltung)

    return render(
        request,
        "core/wanleitung_list.html",
        {"leitungen": leitungen, "can_create_wanleitung": is_super_or_net_admin(user)},
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
            "standort", "standort__verwaltung", "vertrag", "provider_ref", "tarif_ref"
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
        {"leitung": leitung, "can_edit": is_super_or_net_admin(user)},
    )


# ---------------------------- Beauftragungen ----------------------------


@login_required
def beauftragung_list(request):
    user = request.user

    beauftragungen = WanBeauftragung.objects.select_related(
        "standort",
        "standort__verwaltung",
        "bestehende_leitung",
        "erstellt_von",
    ).prefetch_related("angefragte_provider").annotate(provider_count=Count("angefragte_provider", distinct=True))

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        beauftragungen = beauftragungen.filter(standort__verwaltung=user.profile.verwaltung)

    search = request.GET.get("q")
    if search:
        beauftragungen = beauftragungen.filter(
            Q(titel__icontains=search)
            | Q(ticket_nummer__icontains=search)
            | Q(standort__name__icontains=search)
            | Q(standort__standort_code__icontains=search)
        )

    return render(
        request,
        "core/beauftragung_list.html",
        {
            "beauftragungen": beauftragungen,
            "search": search,
            "can_create_beauftragung": can_manage_beauftragung(user),
        },
    )


@login_required
def provider_option_list(request):
    optionen = ProviderZusatzoption.objects.select_related("provider").order_by("provider__name", "name")
    provider_id = request.GET.get("provider")
    if provider_id:
        optionen = optionen.filter(provider_id=provider_id)

    providers = Provider.objects.order_by("name")
    return render(
        request,
        "core/provider_option_list.html",
        {
            "optionen": optionen,
            "providers": providers,
            "selected_provider_id": provider_id,
            "can_create_option": is_super_or_net_admin(request.user),
        },
    )


@login_required
@user_passes_test(is_super_or_net_admin)
def provider_option_create(request):
    provider_id = request.GET.get("provider")
    initial = {"provider": provider_id} if provider_id else None

    if request.method == "POST":
        form = ProviderZusatzoptionForm(request.POST)
        if form.is_valid():
            option = form.save()
            return redirect("core:provider_detail", pk=option.provider_id)
    else:
        form = ProviderZusatzoptionForm(initial=initial)

    return render(request, "core/provider_option_form.html", {"form": form})


@login_required
@user_passes_test(is_super_or_net_admin)
def provider_option_update(request, pk):
    option = get_object_or_404(ProviderZusatzoption.objects.select_related("provider"), pk=pk)

    if request.method == "POST":
        form = ProviderZusatzoptionForm(request.POST, instance=option)
        if form.is_valid():
            option = form.save()
            return redirect("core:provider_detail", pk=option.provider_id)
    else:
        form = ProviderZusatzoptionForm(instance=option)

    return render(
        request,
        "core/provider_option_form.html",
        {"form": form, "is_edit": True, "option": option},
    )


@login_required
@user_passes_test(can_manage_beauftragung)
def beauftragung_create(request):
    user = request.user

    if request.method == "POST":
        form = WanBeauftragungForm(request.POST, user=user)
        if form.is_valid():
            beauftragung = form.save(commit=False)
            if not beauftragung.erstellt_von_id:
                beauftragung.erstellt_von = user
            beauftragung.save()
            form.save_m2m()
            _sync_provider_kontexte(beauftragung)
            return redirect("core:beauftragung_detail", pk=beauftragung.pk)
    else:
        form = WanBeauftragungForm(user=user)

    return render(request, "core/beauftragung_form.html", {"form": form})


@login_required
@user_passes_test(can_manage_beauftragung)
def beauftragung_update(request, pk):
    user = request.user
    beauftragung = get_object_or_404(
        WanBeauftragung.objects.select_related("standort", "standort__verwaltung"),
        pk=pk,
    )

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        if beauftragung.standort.verwaltung_id != user.profile.verwaltung_id:
            return render(request, "core/forbidden.html", status=403)

    if request.method == "POST":
        form = WanBeauftragungForm(request.POST, instance=beauftragung, user=user)
        if form.is_valid():
            beauftragung = form.save(commit=False)
            if not beauftragung.erstellt_von_id:
                beauftragung.erstellt_von = user
            beauftragung.save()
            form.save_m2m()
            _sync_provider_kontexte(beauftragung)
            return redirect("core:beauftragung_detail", pk=beauftragung.pk)
    else:
        form = WanBeauftragungForm(instance=beauftragung, user=user)

    return render(
        request,
        "core/beauftragung_form.html",
        {"form": form, "is_edit": True, "beauftragung": beauftragung},
    )


@login_required
def beauftragung_detail(request, pk):
    user = request.user
    beauftragung = get_object_or_404(
        WanBeauftragung.objects.select_related(
            "standort",
            "standort__verwaltung",
            "bestehende_leitung",
            "erstellt_von",
        ).prefetch_related(
            "angefragte_provider",
            Prefetch(
                "provider_kontexte",
                queryset=WanBeauftragungProviderKontext.objects.select_related("provider", "tarif").prefetch_related(
                    "zusatzoptionen"
                ),
            ),
        ),
        pk=pk,
    )

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        if beauftragung.standort.verwaltung_id != user.profile.verwaltung_id:
            return render(request, "core/forbidden.html", status=403)

    provider_anfragen = []
    for kontext in beauftragung.provider_kontexte.all():
        provider = kontext.provider
        subject = beauftragung.render_anfrage_betreff(provider)
        body = kontext.render_anfrage_text()
        provider_anfragen.append(
            {
                "kontext": kontext,
                "provider": provider,
                "subject": subject,
                "body": body,
                "mailto_link": (
                    f"mailto:{provider.kontakt_mail or ''}"
                    f"?subject={quote(subject)}&body={quote(body)}"
                ),
            }
        )

    return render(
        request,
        "core/beauftragung_detail.html",
        {
            "beauftragung": beauftragung,
            "can_edit": can_manage_beauftragung(user),
            "provider_anfragen": provider_anfragen,
        },
    )


@login_required
@user_passes_test(can_manage_beauftragung)
def beauftragung_provider_kontext_update(request, beauftragung_pk, provider_pk):
    user = request.user
    beauftragung = get_object_or_404(
        WanBeauftragung.objects.select_related("standort", "standort__verwaltung"),
        pk=beauftragung_pk,
    )

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        if beauftragung.standort.verwaltung_id != user.profile.verwaltung_id:
            return render(request, "core/forbidden.html", status=403)

    kontext = get_object_or_404(
        WanBeauftragungProviderKontext.objects.select_related("beauftragung", "provider"),
        beauftragung_id=beauftragung_pk,
        provider_id=provider_pk,
    )

    if request.method == "POST":
        form = WanBeauftragungProviderKontextForm(request.POST, instance=kontext)
        if form.is_valid():
            form.save()
            return redirect("core:beauftragung_detail", pk=beauftragung_pk)
    else:
        form = WanBeauftragungProviderKontextForm(instance=kontext)

    return render(
        request,
        "core/beauftragung_provider_kontext_form.html",
        {"form": form, "beauftragung": beauftragung, "provider": kontext.provider, "kontext": kontext},
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
        {"vertraege": vertraege, "can_create_vertrag": is_super_or_net_admin(user)},
    )


@login_required
@user_passes_test(is_super_or_net_admin)
def vertrag_create(request):
    user = request.user

    if request.method == "POST":
        form = VertragForm(request.POST, user=user)
        if form.is_valid():
            vertrag = form.save()
            return redirect("core:vertrag_detail", pk=vertrag.pk)
    else:
        form = VertragForm(user=user)

    return render(request, "core/vertrag_form.html", {"form": form})


@login_required
@user_passes_test(is_super_or_net_admin)
def vertrag_update(request, pk):
    user = request.user
    vertrag = get_object_or_404(Vertrag, pk=pk)

    if request.method == "POST":
        form = VertragForm(request.POST, instance=vertrag, user=user)
        if form.is_valid():
            vertrag = form.save()
            return redirect("core:vertrag_detail", pk=vertrag.pk)
    else:
        form = VertragForm(instance=vertrag, user=user)

    return render(
        request,
        "core/vertrag_form.html",
        {"form": form, "is_edit": True, "vertrag": vertrag},
    )


@login_required
def vertrag_detail(request, pk):
    vertrag = get_object_or_404(Vertrag.objects.select_related("verwaltung", "provider_ref"), pk=pk)
    user = request.user

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        if vertrag.verwaltung_id != user.profile.verwaltung_id:
            return render(request, "core/forbidden.html", status=403)

    leitungen = vertrag.leitungen.select_related(
        "standort", "standort__verwaltung", "provider_ref", "tarif_ref"
    )

    return render(
        request,
        "core/vertrag_detail.html",
        {"vertrag": vertrag, "leitungen": leitungen, "can_edit": is_super_or_net_admin(user)},
    )
