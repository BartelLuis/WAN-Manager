from decimal import Decimal
import csv
import io
import json
from datetime import timedelta
from urllib.parse import quote

from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.db import transaction

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
    Erinnerung,
    AuditLog,
    DokumentAnhang,
    ObjektNotiz,
    UserNotification,
    SavedFilter,
    UserProfile,
    GlobalSettings,
    LeitungsStoerung,
    ProviderBewertung,
    DokumentMappe,
    DokumentVersion,
    ObjektBerechtigung,
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
    CsvImportForm,
    SavedFilterForm,
    LeitungsStoerungForm,
    ProviderBewertungForm,
    DokumentMappeForm,
    DokumentVersionForm,
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


def can_approve_beauftragung(user) -> bool:
    return (
        is_super_or_net_admin(user)
        or user_in_group(user, "GENEHMIGER")
    )


def _resolve_verwaltung_id_for_object(obj):
    if hasattr(obj, "verwaltung_id") and obj.verwaltung_id:
        return obj.verwaltung_id
    standort = getattr(obj, "standort", None)
    if standort and getattr(standort, "verwaltung_id", None):
        return standort.verwaltung_id
    wanleitung = getattr(obj, "wanleitung", None)
    if wanleitung and getattr(wanleitung, "standort_id", None):
        return getattr(wanleitung.standort, "verwaltung_id", None)
    beauftragung = getattr(obj, "beauftragung", None)
    if beauftragung and getattr(beauftragung, "standort_id", None):
        return getattr(beauftragung.standort, "verwaltung_id", None)
    mappe_obj = getattr(obj, "content_object", None)
    if mappe_obj:
        return _resolve_verwaltung_id_for_object(mappe_obj)
    return None


def has_action_permission(user, action: str, obj=None) -> bool:
    if not user.is_authenticated:
        return False
    if is_super_or_net_admin(user):
        return True

    if obj is not None:
        ct = ContentType.objects.get_for_model(obj.__class__)
        rule = (
            ObjektBerechtigung.objects.filter(
                user=user,
                action=action,
                content_type=ct,
                object_id=obj.pk,
            )
            .order_by("-id")
            .first()
        )
        if rule is not None:
            return rule.erlaubt

    if action == ObjektBerechtigung.ACTION_EXPORT:
        return user_in_group(user, "EINKAEUFER") or user_in_group(user, "EINKAUFER")

    if user_in_group(user, "IT-BEAUFTRAGTER"):
        if obj is None:
            return action in {ObjektBerechtigung.ACTION_VIEW, ObjektBerechtigung.ACTION_DOCS}
        own_verwaltung_id = getattr(getattr(user, "profile", None), "verwaltung_id", None)
        obj_verwaltung_id = _resolve_verwaltung_id_for_object(obj)
        if own_verwaltung_id and obj_verwaltung_id and own_verwaltung_id == obj_verwaltung_id:
            return action in {
                ObjektBerechtigung.ACTION_VIEW,
                ObjektBerechtigung.ACTION_EDIT,
                ObjektBerechtigung.ACTION_DOCS,
            }
    return False


def unread_notifications_count(user) -> int:
    if not user.is_authenticated:
        return 0
    return UserNotification.objects.filter(user=user, gelesen=False).count()


def _role_label(user) -> str:
    if user.is_superuser or user_in_group(user, "SUPERADMIN"):
        return "SUPERADMIN"
    if user_in_group(user, "NETZADMIN"):
        return "NETZADMIN"
    if user_in_group(user, "IT-BEAUFTRAGTER"):
        return "IT-BEAUFTRAGTER"
    if user_in_group(user, "EINKAEUFER") or user_in_group(user, "EINKAUFER"):
        return "EINKAEUFER"
    return "USER"


def _smart_provider_suggestions(user, standort=None):
    qs = Provider.objects.none()
    if standort:
        qs = Provider.objects.filter(leitungen__standort=standort)

    if user and hasattr(user, "profile") and user.profile.verwaltung_id:
        qs = qs | Provider.objects.filter(
            beauftragungen__standort__verwaltung_id=user.profile.verwaltung_id
        )
    return qs.distinct().order_by("name")[:5]


def _timeline_for_object(obj):
    ct = ContentType.objects.get_for_model(obj.__class__)
    audits = AuditLog.objects.filter(content_type=ct, object_id=obj.pk)[:30]
    notes = ObjektNotiz.objects.filter(content_type=ct, object_id=obj.pk)[:30]
    docs = DokumentAnhang.objects.filter(content_type=ct, object_id=obj.pk)[:30]
    timeline = []
    for a in audits:
        timeline.append({"kind": "audit", "time": a.created_at, "item": a})
    for n in notes:
        timeline.append({"kind": "note", "time": n.erstellt_am, "item": n})
    for d in docs:
        timeline.append({"kind": "doc", "time": d.hochgeladen_am, "item": d})
    timeline.sort(key=lambda x: x["time"], reverse=True)
    return timeline[:50]


def _send_ticket_email_for_beauftragung(beauftragung, approver):
    settings_obj = GlobalSettings.objects.filter(pk=1).first()
    recipient = (
        (settings_obj.ticket_system_email or "").strip()
        if settings_obj
        else ""
    ) or (getattr(settings, "TICKET_SYSTEM_EMAIL", "") or "").strip()
    if not recipient:
        raise ValueError("Keine Ticketsystem-E-Mail konfiguriert.")

    header_name = (
        (settings_obj.ticket_header_name or "").strip()
        if settings_obj
        else ""
    ) or "X-Ticket-Nummer"
    ticket_nummer = (beauftragung.ticket_nummer or f"WAN-{beauftragung.pk}").strip()

    subject = f"WAN-Beauftragung genehmigt [{ticket_nummer}]"
    body = (
        f"Die WAN-Beauftragung wurde genehmigt.\n\n"
        f"Titel: {beauftragung.titel}\n"
        f"Standort: {beauftragung.standort.name if beauftragung.standort_id else '-'}\n"
        f"Ticketnummer: {ticket_nummer}\n"
        f"Genehmigt von: {approver.username}\n"
        f"Genehmigt am: {timezone.localtime(timezone.now()).strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Bitte Ticket weiterverarbeiten."
    )
    email = EmailMessage(
        subject=subject,
        body=body,
        to=[recipient],
        headers={header_name: ticket_nummer},
    )
    email.send(fail_silently=False)


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
    today = timezone.localdate()

    vertrags_fristen = Vertrag.objects.filter(
        laufzeit_bis__isnull=False,
        laufzeit_bis__lte=today + timedelta(days=30),
    )
    offene_beauftragungen = WanBeauftragung.objects.exclude(
        status__in=[
            WanBeauftragung.STATUS_UMGESETZT,
            WanBeauftragung.STATUS_ABGELEHNT,
            WanBeauftragung.STATUS_STORNIERT,
        ]
    )
    offene_erinnerungen = Erinnerung.objects.exclude(status=Erinnerung.STATUS_ERLEDIGT)

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung_id:
        vertrags_fristen = vertrags_fristen.filter(verwaltung_id=user.profile.verwaltung_id)
        offene_beauftragungen = offene_beauftragungen.filter(standort__verwaltung_id=user.profile.verwaltung_id)
        offene_erinnerungen = offene_erinnerungen.filter(
            Q(vertrag__verwaltung_id=user.profile.verwaltung_id)
            | Q(beauftragung__standort__verwaltung_id=user.profile.verwaltung_id)
        )

    unterversorgt = 0
    standorte = Standort.objects.prefetch_related("leitungen")
    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung_id:
        standorte = standorte.filter(verwaltung_id=user.profile.verwaltung_id)
    for s in standorte:
        required = int((s.arbeitsplaetze or 0) * WAN_MBIT_PER_AP_DOWN)
        if required <= 0:
            continue
        best = max([l.bandbreite_down_mbit or 0 for l in s.leitungen.all()] + [0])
        if best < required:
            unterversorgt += 1

    context = {
        "verwaltungen": verwaltungen,
        "role_label": _role_label(user),
        "unread_notifications": unread_notifications_count(user),
        "risk_cards": [
            {"label": "Offene Erinnerungen", "value": offene_erinnerungen.count(), "link": "core:erinnerung_list"},
            {"label": "Offene Beauftragungen", "value": offene_beauftragungen.count(), "link": "core:beauftragung_list"},
            {"label": "Verträge <= 30 Tage", "value": vertrags_fristen.count(), "link": "core:vertrag_list"},
            {"label": "Unterversorgte Standorte", "value": unterversorgt, "link": "core:standort_list"},
        ],
    }
    return render(request, "core/dashboard.html", context)


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
        {
            "standort": standort,
            "leitungen": leitungen,
            "can_edit": is_super_or_net_admin(user),
            "timeline": _timeline_for_object(standort),
        },
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
        {"leitung": leitung, "can_edit": is_super_or_net_admin(user), "timeline": _timeline_for_object(leitung)},
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

    if request.method == "POST" and can_manage_beauftragung(user):
        action = request.POST.get("bulk_action")
        ids = request.POST.getlist("selected")
        if ids:
            qs = beauftragungen.filter(id__in=ids)
            if action in dict(WanBeauftragung.STATUS_CHOICES):
                qs.update(status=action)
                messages.success(request, f"{qs.count()} Beauftragungen aktualisiert.")
            elif action == "delete":
                count = qs.count()
                qs.delete()
                messages.success(request, f"{count} Beauftragungen gelöscht.")
        return redirect("core:beauftragung_list")

    search = request.GET.get("q")
    if search:
        beauftragungen = beauftragungen.filter(
            Q(titel__icontains=search)
            | Q(ticket_nummer__icontains=search)
            | Q(standort__name__icontains=search)
            | Q(standort__standort_code__icontains=search)
        )

    saved_filters = SavedFilter.objects.filter(user=user, target=SavedFilter.TARGET_BEAUFTRAGUNG)

    return render(
        request,
        "core/beauftragung_list.html",
        {
            "beauftragungen": beauftragungen,
            "search": search,
            "can_create_beauftragung": can_manage_beauftragung(user),
            "saved_filters": saved_filters,
            "status_choices": WanBeauftragung.STATUS_CHOICES,
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
        standort_id = request.GET.get("standort")
        standort = Standort.objects.filter(pk=standort_id).first() if standort_id else None
        suggestions = _smart_provider_suggestions(user, standort)
        if suggestions:
            form.initial.setdefault("angefragte_provider", [p.pk for p in suggestions])

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
                "total_cost": (kontext.angebot_kosten_monat_netto or Decimal("0.00")) + (kontext.angebot_kosten_einmalig_netto or Decimal("0.00")),
            }
        )

    recommended = None
    priced = [a for a in provider_anfragen if a["kontext"].angebot_kosten_monat_netto is not None or a["kontext"].angebot_kosten_einmalig_netto is not None]
    if priced:
        recommended = sorted(priced, key=lambda x: x["total_cost"])[0]

    timeline = _timeline_for_object(beauftragung)

    return render(
        request,
        "core/beauftragung_detail.html",
        {
            "beauftragung": beauftragung,
            "can_edit": can_manage_beauftragung(user),
            "can_approve": can_approve_beauftragung(user),
            "provider_anfragen": provider_anfragen,
            "recommended_provider_id": recommended["provider"].id if recommended else None,
            "timeline": timeline,
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


@login_required
@user_passes_test(can_manage_beauftragung)
def beauftragung_provider_anfrage_sent(request, beauftragung_pk, provider_pk):
    kontext = get_object_or_404(
        WanBeauftragungProviderKontext,
        beauftragung_id=beauftragung_pk,
        provider_id=provider_pk,
    )
    kontext.anfrage_gesendet_am = timezone.now()
    kontext.anfrage_gesendet_von = request.user
    kontext.save(update_fields=["anfrage_gesendet_am", "anfrage_gesendet_von"])
    messages.success(request, "Anfrage als gesendet markiert.")
    return redirect("core:beauftragung_detail", pk=beauftragung_pk)


@login_required
@user_passes_test(can_approve_beauftragung)
def beauftragung_approve(request, pk):
    beauftragung = get_object_or_404(WanBeauftragung, pk=pk)
    if not has_action_permission(request.user, ObjektBerechtigung.ACTION_APPROVE, beauftragung):
        return render(request, "core/forbidden.html", status=403)

    if request.method != "POST":
        return redirect("core:beauftragung_detail", pk=pk)

    if beauftragung.genehmigt:
        messages.info(request, "Diese Beauftragung ist bereits genehmigt.")
        return redirect("core:beauftragung_detail", pk=pk)

    note = (request.POST.get("genehmigungs_notiz") or "").strip()
    try:
        with transaction.atomic():
            beauftragung.genehmigt = True
            beauftragung.genehmigt_von = request.user
            beauftragung.genehmigt_am = timezone.now()
            beauftragung.genehmigungs_notiz = note or None
            if beauftragung.status in {WanBeauftragung.STATUS_OFFEN, WanBeauftragung.STATUS_IN_PRUEFUNG}:
                beauftragung.status = WanBeauftragung.STATUS_BEAUFTRAGT
            _send_ticket_email_for_beauftragung(beauftragung, request.user)
            beauftragung.ticket_gesendet_am = timezone.now()
            beauftragung.save()
        messages.success(request, "Genehmigt und ans Ticketsystem gesendet.")
    except Exception as exc:
        messages.error(request, f"Genehmigung fehlgeschlagen: {exc}")

    return redirect("core:beauftragung_detail", pk=pk)


@login_required
def my_tasks(request):
    user = request.user
    today = timezone.localdate()
    my_reminders = Erinnerung.objects.filter(zugewiesen_an=user).order_by("status", "faellig_am")
    my_beauftragungen = WanBeauftragung.objects.filter(
        Q(erstellt_von=user) | Q(provider_kontexte__anfrage_gesendet_von=user)
    ).distinct().order_by("-angefragt_am")
    overdues = my_reminders.filter(status=Erinnerung.STATUS_OFFEN, faellig_am__lt=today).count()

    return render(
        request,
        "core/my_tasks.html",
        {
            "my_reminders": my_reminders[:50],
            "my_beauftragungen": my_beauftragungen[:30],
            "overdues": overdues,
            "unread_notifications": unread_notifications_count(user),
        },
    )


@login_required
def notification_list(request):
    qs = UserNotification.objects.filter(user=request.user)
    if request.method == "POST":
        if request.POST.get("mark_all") == "1":
            qs.filter(gelesen=False).update(gelesen=True)
            messages.success(request, "Alle Benachrichtigungen als gelesen markiert.")
            return redirect("core:notification_list")
    return render(request, "core/notification_list.html", {"notifications": qs[:200]})


@login_required
def notification_mark_read(request, pk):
    notification = get_object_or_404(UserNotification, pk=pk, user=request.user)
    notification.gelesen = True
    notification.save(update_fields=["gelesen"])
    if notification.link:
        return redirect(notification.link)
    return redirect("core:notification_list")


@login_required
def save_filter(request):
    if request.method != "POST":
        return redirect("core:dashboard")
    form = SavedFilterForm(request.POST)
    if form.is_valid():
        saved = form.save(commit=False)
        saved.user = request.user
        saved.save()
        messages.success(request, "Filter gespeichert.")
    else:
        messages.error(request, "Filter konnte nicht gespeichert werden.")
    target = request.POST.get("target")
    if target == SavedFilter.TARGET_BEAUFTRAGUNG:
        return redirect("core:beauftragung_list")
    if target == SavedFilter.TARGET_ERINNERUNG:
        return redirect("core:erinnerung_list")
    return redirect("core:dashboard")


@login_required
def apply_filter(request, pk):
    saved = get_object_or_404(SavedFilter, pk=pk, user=request.user)
    if saved.target == SavedFilter.TARGET_BEAUFTRAGUNG:
        return redirect(f"/beauftragungen/?{saved.querystring}")
    if saved.target == SavedFilter.TARGET_ERINNERUNG:
        return redirect(f"/erinnerungen/?{saved.querystring}")
    if saved.target == SavedFilter.TARGET_STANDORT:
        return redirect(f"/standorte/?{saved.querystring}")
    return redirect("core:dashboard")


@login_required
def stoerung_list(request):
    qs = LeitungsStoerung.objects.select_related(
        "wanleitung",
        "wanleitung__standort",
        "wanleitung__standort__verwaltung",
        "provider",
    )
    user = request.user
    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung_id:
        qs = qs.filter(wanleitung__standort__verwaltung_id=user.profile.verwaltung_id)

    status = request.GET.get("status")
    if status in dict(LeitungsStoerung.STATUS_CHOICES):
        qs = qs.filter(status=status)

    return render(
        request,
        "core/stoerung_list.html",
        {
            "stoerungen": qs.order_by("status", "-geoeffnet_am"),
            "status": status or "",
            "status_choices": LeitungsStoerung.STATUS_CHOICES,
            "can_create_stoerung": can_manage_beauftragung(user),
        },
    )


@login_required
@user_passes_test(can_manage_beauftragung)
def stoerung_create(request):
    if request.method == "POST":
        form = LeitungsStoerungForm(request.POST)
        if form.is_valid():
            stoerung = form.save(commit=False)
            if not has_action_permission(request.user, ObjektBerechtigung.ACTION_EDIT, stoerung.wanleitung):
                return render(request, "core/forbidden.html", status=403)
            stoerung.erstellt_von = request.user
            if not stoerung.provider_id and stoerung.wanleitung.provider_ref_id:
                stoerung.provider_id = stoerung.wanleitung.provider_ref_id
            stoerung.save()
            return redirect("core:stoerung_detail", pk=stoerung.pk)
    else:
        form = LeitungsStoerungForm()

    return render(request, "core/stoerung_form.html", {"form": form})


@login_required
def stoerung_detail(request, pk):
    stoerung = get_object_or_404(
        LeitungsStoerung.objects.select_related(
            "wanleitung",
            "wanleitung__standort",
            "wanleitung__standort__verwaltung",
            "provider",
        ),
        pk=pk,
    )
    if not has_action_permission(request.user, ObjektBerechtigung.ACTION_VIEW, stoerung):
        return render(request, "core/forbidden.html", status=403)
    return render(
        request,
        "core/stoerung_detail.html",
        {"stoerung": stoerung, "can_edit": can_manage_beauftragung(request.user)},
    )


@login_required
@user_passes_test(can_manage_beauftragung)
def stoerung_update(request, pk):
    stoerung = get_object_or_404(LeitungsStoerung, pk=pk)
    if not has_action_permission(request.user, ObjektBerechtigung.ACTION_EDIT, stoerung):
        return render(request, "core/forbidden.html", status=403)

    if request.method == "POST":
        form = LeitungsStoerungForm(request.POST, instance=stoerung)
        if form.is_valid():
            form.save()
            return redirect("core:stoerung_detail", pk=stoerung.pk)
    else:
        form = LeitungsStoerungForm(instance=stoerung)

    return render(request, "core/stoerung_form.html", {"form": form, "is_edit": True, "stoerung": stoerung})


@login_required
def provider_scorecard(request):
    user = request.user
    if request.method == "POST" and can_manage_beauftragung(user):
        form = ProviderBewertungForm(request.POST)
        if form.is_valid():
            bewertung = form.save(commit=False)
            bewertung.erstellt_von = user
            bewertung.save()
            messages.success(request, "Provider-Bewertung gespeichert.")
            return redirect("core:provider_scorecard")
    else:
        form = ProviderBewertungForm()

    providers_qs = Provider.objects.annotate(
        total_score=Coalesce(Sum("bewertungen__gesamt_score"), Value(Decimal("0.00"))),
        bewertung_count=Count("bewertungen"),
    ).order_by("name")
    providers = []
    for p in providers_qs:
        count = int(p.bewertung_count or 0)
        avg = float(p.total_score or 0) / count if count else 0.0
        providers.append({"provider": p, "avg_score": round(avg, 2), "bewertung_count": count})
    providers.sort(key=lambda x: x["avg_score"], reverse=True)

    return render(
        request,
        "core/provider_scorecard.html",
        {
            "providers": providers,
            "form": form,
            "bewertungen": ProviderBewertung.objects.select_related("provider", "beauftragung", "erstellt_von")[:100],
            "can_rate": can_manage_beauftragung(user),
        },
    )


@login_required
def ops_calendar(request):
    user = request.user
    today = timezone.localdate()

    erinnerungen = Erinnerung.objects.exclude(status=Erinnerung.STATUS_ERLEDIGT).select_related("vertrag", "beauftragung")
    vertraege = Vertrag.objects.filter(laufzeit_bis__isnull=False)
    beauftragungen = WanBeauftragung.objects.exclude(status__in=[WanBeauftragung.STATUS_UMGESETZT, WanBeauftragung.STATUS_ABGELEHNT, WanBeauftragung.STATUS_STORNIERT])
    stoerungen = LeitungsStoerung.objects.exclude(status=LeitungsStoerung.STATUS_BEHOBEN).select_related("wanleitung", "wanleitung__standort")

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung_id:
        verw_id = user.profile.verwaltung_id
        erinnerungen = erinnerungen.filter(Q(vertrag__verwaltung_id=verw_id) | Q(beauftragung__standort__verwaltung_id=verw_id))
        vertraege = vertraege.filter(verwaltung_id=verw_id)
        beauftragungen = beauftragungen.filter(standort__verwaltung_id=verw_id)
        stoerungen = stoerungen.filter(wanleitung__standort__verwaltung_id=verw_id)

    events = []
    for e in erinnerungen[:200]:
        events.append({"datum": e.faellig_am, "typ": "Erinnerung", "titel": e.titel, "link": "/erinnerungen/"})
    for v in vertraege.filter(laufzeit_bis__lte=today + timedelta(days=180))[:200]:
        events.append({"datum": v.laufzeit_bis, "typ": "Vertrag", "titel": f"Vertrag endet: {v.vertragsnummer}", "link": f"/vertraege/{v.pk}/"})
    for b in beauftragungen.filter(umsetzung_bis__isnull=False)[:200]:
        events.append({"datum": b.umsetzung_bis, "typ": "Beauftragung", "titel": b.titel, "link": f"/beauftragungen/{b.pk}/"})
    for s in stoerungen[:200]:
        events.append({"datum": timezone.localtime(s.erwartet_behebung_bis).date() if s.erwartet_behebung_bis else today, "typ": "Störung", "titel": s.titel, "link": f"/stoerungen/{s.pk}/"})

    events.sort(key=lambda x: x["datum"])
    return render(request, "core/ops_calendar.html", {"events": events[:400], "today": today})


@login_required
def reports_interactive(request):
    user = request.user
    if not has_action_permission(user, ObjektBerechtigung.ACTION_EXPORT):
        return render(request, "core/forbidden.html", status=403)

    vertraege = Vertrag.objects.all()
    beauftragungen = WanBeauftragung.objects.all()
    stoerungen = LeitungsStoerung.objects.all()
    standorte = Standort.objects.prefetch_related("leitungen")

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung_id:
        verw_id = user.profile.verwaltung_id
        vertraege = vertraege.filter(verwaltung_id=verw_id)
        beauftragungen = beauftragungen.filter(standort__verwaltung_id=verw_id)
        stoerungen = stoerungen.filter(wanleitung__standort__verwaltung_id=verw_id)
        standorte = standorte.filter(verwaltung_id=verw_id)

    costs_by_provider = (
        vertraege.values("provider")
        .annotate(total=Coalesce(Sum("kosten_monat_netto"), Value(Decimal("0.00"))))
        .order_by("-total")[:10]
    )
    status_data = beauftragungen.values("status").annotate(total=Count("id")).order_by("status")

    sla_broken = sum(1 for s in stoerungen if s.ist_sla_verletzt)
    under_supplied = 0
    for standort in standorte:
        required = int((standort.arbeitsplaetze or 0) * WAN_MBIT_PER_AP_DOWN)
        if required <= 0:
            continue
        best = max([l.bandbreite_down_mbit or 0 for l in standort.leitungen.all()] + [0])
        if best < required:
            under_supplied += 1

    chart_payload = {
        "cost_labels": [row["provider"] or "Unbekannt" for row in costs_by_provider],
        "cost_values": [float(row["total"] or 0) for row in costs_by_provider],
        "status_labels": [row["status"] for row in status_data],
        "status_values": [row["total"] for row in status_data],
    }

    return render(
        request,
        "core/reports_interactive.html",
        {
            "chart_payload": json.dumps(chart_payload),
            "kpi_sla_broken": sla_broken,
            "kpi_under_supplied": under_supplied,
            "kpi_open_stoerungen": stoerungen.exclude(status=LeitungsStoerung.STATUS_BEHOBEN).count(),
        },
    )


@login_required
def dokument_mappe_create(request, model_name, object_id):
    model_map = {
        "beauftragung": WanBeauftragung,
        "vertrag": Vertrag,
        "leitung": WanLeitung,
        "standort": Standort,
    }
    model = model_map.get(model_name)
    if not model:
        return redirect("core:dashboard")
    obj = get_object_or_404(model, pk=object_id)
    if not has_action_permission(request.user, ObjektBerechtigung.ACTION_DOCS, obj):
        return render(request, "core/forbidden.html", status=403)

    if request.method == "POST":
        form = DokumentMappeForm(request.POST)
        if form.is_valid():
            mappe = form.save(commit=False)
            mappe.content_type = ContentType.objects.get_for_model(model)
            mappe.object_id = obj.pk
            mappe.erstellt_von = request.user
            mappe.save()
            messages.success(request, "Dokumentenmappe erstellt.")
            return redirect("core:dokument_mappe_detail", pk=mappe.pk)
    else:
        form = DokumentMappeForm()

    return render(request, "core/dokument_mappe_form.html", {"form": form, "obj": obj})


@login_required
def dokument_mappe_detail(request, pk):
    mappe = get_object_or_404(DokumentMappe.objects.prefetch_related("versionen"), pk=pk)
    if not has_action_permission(request.user, ObjektBerechtigung.ACTION_DOCS, mappe):
        return render(request, "core/forbidden.html", status=403)

    if request.method == "POST":
        form = DokumentVersionForm(request.POST, request.FILES)
        if form.is_valid():
            version = form.save(commit=False)
            version.mappe = mappe
            version.hochgeladen_von = request.user
            version.save()
            messages.success(request, "Dokumentversion gespeichert.")
            return redirect("core:dokument_mappe_detail", pk=pk)
    else:
        next_version = (mappe.versionen.first().version + 1) if mappe.versionen.exists() else 1
        form = DokumentVersionForm(initial={"version": next_version})

    return render(
        request,
        "core/dokument_mappe_detail.html",
        {"mappe": mappe, "form": form, "versionen": mappe.versionen.all()},
    )


@login_required
def add_object_note(request, model_name, object_id):
    model_map = {
        "beauftragung": WanBeauftragung,
        "vertrag": Vertrag,
        "leitung": WanLeitung,
        "standort": Standort,
    }
    model = model_map.get(model_name)
    if not model:
        return redirect("core:dashboard")
    obj = get_object_or_404(model, pk=object_id)
    text = (request.POST.get("text") or "").strip()
    if text:
        ObjektNotiz.objects.create(
            content_type=ContentType.objects.get_for_model(model),
            object_id=obj.pk,
            text=text,
            erstellt_von=request.user,
        )
        messages.success(request, "Notiz gespeichert.")

    redirect_map = {
        "beauftragung": "core:beauftragung_detail",
        "vertrag": "core:vertrag_detail",
        "leitung": "core:wanleitung_detail",
        "standort": "core:standort_detail",
    }
    return redirect(redirect_map[model_name], pk=obj.pk)


@login_required
def erinnerung_list(request):
    user = request.user
    qs = Erinnerung.objects.select_related("vertrag", "beauftragung", "zugewiesen_an")

    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        qs = qs.filter(
            Q(vertrag__verwaltung_id=user.profile.verwaltung_id)
            | Q(beauftragung__standort__verwaltung_id=user.profile.verwaltung_id)
        )

    if request.method == "POST":
        action = request.POST.get("bulk_action")
        ids = request.POST.getlist("selected")
        target_user_id = request.POST.get("assign_user")
        selected = qs.filter(id__in=ids)
        if action in dict(Erinnerung.STATUS_CHOICES):
            selected.update(status=action)
            messages.success(request, f"{selected.count()} Erinnerungen aktualisiert.")
        elif action == "assign_me":
            selected.update(zugewiesen_an=user)
            messages.success(request, f"{selected.count()} Erinnerungen dir zugewiesen.")
        elif action == "assign_user" and target_user_id:
            selected.update(zugewiesen_an_id=target_user_id)
            messages.success(request, f"{selected.count()} Erinnerungen zugewiesen.")
        return redirect("core:erinnerung_list")

    show = request.GET.get("show", "offen")
    today = timezone.localdate()
    if show == "offen":
        qs = qs.exclude(status=Erinnerung.STATUS_ERLEDIGT)
    if show == "ueberfaellig":
        qs = qs.filter(status=Erinnerung.STATUS_OFFEN, faellig_am__lt=today)

    return render(
        request,
        "core/erinnerung_list.html",
        {
            "erinnerungen": qs.order_by("faellig_am", "id"),
            "show": show,
            "today": today,
            "saved_filters": SavedFilter.objects.filter(user=user, target=SavedFilter.TARGET_ERINNERUNG),
            "status_choices": Erinnerung.STATUS_CHOICES,
            "assignable_users": User.objects.filter(is_active=True).order_by("username")[:100],
        },
    )


@login_required
def report_vertraege_csv(request):
    user = request.user
    if not has_action_permission(user, ObjektBerechtigung.ACTION_EXPORT):
        return render(request, "core/forbidden.html", status=403)
    vertraege = Vertrag.objects.select_related("verwaltung", "provider_ref").order_by("verwaltung__kuerzel", "provider", "vertragsnummer")
    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        vertraege = vertraege.filter(verwaltung_id=user.profile.verwaltung_id)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="report_vertraege.csv"'
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Verwaltung",
            "Provider",
            "Vertragsnummer",
            "Laufzeit von",
            "Laufzeit bis",
            "Kündigungsfrist (Tage)",
            "Kosten monatlich netto",
            "Kosten einmalig netto",
        ]
    )
    for v in vertraege:
        writer.writerow(
            [
                v.verwaltung.kuerzel or v.verwaltung.name,
                v.provider,
                v.vertragsnummer,
                v.laufzeit_von or "",
                v.laufzeit_bis or "",
                v.kuendigungsfrist_tage or "",
                v.kosten_monat_netto or "",
                v.kosten_einmalig_netto or "",
            ]
        )
    return response


@login_required
def report_beauftragungen_csv(request):
    user = request.user
    if not has_action_permission(user, ObjektBerechtigung.ACTION_EXPORT):
        return render(request, "core/forbidden.html", status=403)
    beauftragungen = WanBeauftragung.objects.select_related("standort", "standort__verwaltung", "erstellt_von").prefetch_related("angefragte_provider")
    if user_in_group(user, "IT-BEAUFTRAGTER") and hasattr(user, "profile") and user.profile.verwaltung:
        beauftragungen = beauftragungen.filter(standort__verwaltung_id=user.profile.verwaltung_id)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="report_beauftragungen.csv"'
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Angefragt am",
            "Status",
            "Priorität",
            "Verwaltung",
            "Standort",
            "Titel",
            "Ticket",
            "Provider",
            "Umsetzung bis",
        ]
    )
    for b in beauftragungen.order_by("-angefragt_am", "-id"):
        writer.writerow(
            [
                b.angefragt_am or "",
                b.get_status_display(),
                b.get_prioritaet_display(),
                b.standort.verwaltung.kuerzel or b.standort.verwaltung.name,
                b.standort.standort_code or b.standort.name,
                b.titel,
                b.ticket_nummer or "",
                ", ".join(b.angefragte_provider.values_list("name", flat=True)),
                b.umsetzung_bis or "",
            ]
        )
    return response


@login_required
@user_passes_test(is_super_or_net_admin)
def import_vertraege_csv(request):
    if request.method == "POST":
        form = CsvImportForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data["csv_file"]
            decoded = io.StringIO(file.read().decode("utf-8-sig"))
            reader = csv.DictReader(decoded, delimiter=";")
            created = 0
            errors = 0
            for row in reader:
                try:
                    verwaltung = Verwaltung.objects.filter(
                        Q(kuerzel=row.get("verwaltung")) | Q(name=row.get("verwaltung"))
                    ).first()
                    if not verwaltung:
                        errors += 1
                        continue
                    provider_ref = Provider.objects.filter(name=row.get("provider")).first()
                    Vertrag.objects.create(
                        verwaltung=verwaltung,
                        provider_ref=provider_ref,
                        provider=row.get("provider") or (provider_ref.kuerzel if provider_ref else "Unbekannt"),
                        vertragsnummer=row.get("vertragsnummer") or "",
                        kostenstelle=row.get("kostenstelle") or None,
                    )
                    created += 1
                except Exception:
                    errors += 1
            messages.success(request, f"Import beendet: {created} erstellt, {errors} Fehler.")
            return redirect("core:vertrag_list")
    else:
        form = CsvImportForm()
    return render(request, "core/import_vertraege.html", {"form": form})


@login_required
def erinnerung_quick_done(request, pk):
    erinnerung = get_object_or_404(Erinnerung, pk=pk)
    erinnerung.status = Erinnerung.STATUS_ERLEDIGT
    erinnerung.zugewiesen_an = request.user
    erinnerung.save(update_fields=["status", "zugewiesen_an"])
    messages.success(request, "Erinnerung als erledigt markiert.")
    return redirect("core:erinnerung_list")


@login_required
@user_passes_test(can_manage_beauftragung)
def beauftragung_set_status(request, pk, status):
    beauftragung = get_object_or_404(WanBeauftragung, pk=pk)
    if not has_action_permission(request.user, ObjektBerechtigung.ACTION_EDIT, beauftragung):
        return render(request, "core/forbidden.html", status=403)
    valid = {value for value, _label in WanBeauftragung.STATUS_CHOICES}
    if status in valid:
        beauftragung.status = status
        beauftragung.save(update_fields=["status"])
        messages.success(request, f"Status auf {beauftragung.get_status_display()} gesetzt.")
    return redirect("core:beauftragung_detail", pk=pk)


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
        {
            "vertrag": vertrag,
            "leitungen": leitungen,
            "can_edit": is_super_or_net_admin(user),
            "timeline": _timeline_for_object(vertrag),
        },
    )
