from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import WanBeauftragungForm, WanLeitungForm
from .models import (
    Erinnerung,
    SavedFilter,
    UserNotification,
    Provider,
    Standort,
    Tarif,
    Vertrag,
    Verwaltung,
    WanBeauftragung,
)


class WanLeitungFormTests(TestCase):
    def setUp(self):
        self.verwaltung = Verwaltung.objects.create(name="Musterverwaltung", kuerzel="MUS")
        self.standort = Standort.objects.create(
            verwaltung=self.verwaltung,
            name="Rathaus",
            adresse_ort="Neustadt",
            adresse_strasse="Hauptstraße 1",
        )
        self.provider = Provider.objects.create(name="Provider A", kuerzel="PA")
        self.tarif = Tarif.objects.create(
            provider=self.provider,
            name="Business 500",
            bandbreite_down_mbit=500,
            bandbreite_up_mbit=100,
            medium="fibre",
        )

    def test_save_uebernimmt_tarif_werte(self):
        form = WanLeitungForm(
            data={
                "standort": self.standort.pk,
                "tarif_ref": self.tarif.pk,
                "medium": "fibre",
                "status": "aktiv",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        leitung = form.save()

        self.assertEqual(leitung.provider_ref, self.provider)
        self.assertEqual(leitung.provider, "PA")
        self.assertEqual(leitung.bezeichnung, "Business 500")
        self.assertEqual(leitung.bandbreite_down_mbit, 500)
        self.assertEqual(leitung.bandbreite_up_mbit, 100)

    def test_save_setzt_provider_aus_provider_ref_ohne_tarif(self):
        form = WanLeitungForm(
            data={
                "standort": self.standort.pk,
                "provider_ref": self.provider.pk,
                "medium": "dsl",
                "status": "aktiv",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        leitung = form.save()

        self.assertEqual(leitung.provider, "PA")
        self.assertIsNone(leitung.tarif_ref)

    def test_form_rejects_vlan_out_of_range(self):
        form = WanLeitungForm(
            data={
                "standort": self.standort.pk,
                "provider_ref": self.provider.pk,
                "medium": "dsl",
                "status": "aktiv",
                "vlan_id": 5000,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("vlan_id", form.errors)


class WanBeauftragungWorkflowTests(TestCase):
    def setUp(self):
        self.verwaltung = Verwaltung.objects.create(name="Musterverwaltung", kuerzel="MUS")
        self.standort = Standort.objects.create(
            verwaltung=self.verwaltung,
            name="Rathaus",
            adresse_ort="Neustadt",
            adresse_strasse="Hauptstraße 1",
        )
        self.provider = Provider.objects.create(name="Provider A", kuerzel="PA")

    def test_beauftragt_requires_provider_and_bandwidth(self):
        form = WanBeauftragungForm(
            data={
                "standort": self.standort.pk,
                "titel": "Neue Leitung",
                "status": WanBeauftragung.STATUS_BEAUFTRAGT,
                "prioritaet": WanBeauftragung.PRIO_NORMAL,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("angefragte_provider", form.errors)
        self.assertIn("bedarf_down_mbit", form.errors)

    def test_beauftragt_is_valid_with_provider_and_bandwidth(self):
        form = WanBeauftragungForm(
            data={
                "standort": self.standort.pk,
                "titel": "Neue Leitung",
                "status": WanBeauftragung.STATUS_BEAUFTRAGT,
                "prioritaet": WanBeauftragung.PRIO_NORMAL,
                "bedarf_down_mbit": 100,
                "angefragte_provider": [self.provider.pk],
            }
        )
        self.assertTrue(form.is_valid(), form.errors)


class ReminderCommandTests(TestCase):
    def setUp(self):
        self.verwaltung = Verwaltung.objects.create(name="Musterverwaltung", kuerzel="MUS")
        self.standort = Standort.objects.create(
            verwaltung=self.verwaltung,
            name="Rathaus",
            adresse_ort="Neustadt",
            adresse_strasse="Hauptstraße 1",
        )
        self.provider = Provider.objects.create(name="Provider A", kuerzel="PA")
        self.user = User.objects.create_user(username="tester", password="test")

    def test_generate_erinnerungen_creates_entries(self):
        today = timezone.localdate()
        Vertrag.objects.create(
            verwaltung=self.verwaltung,
            provider_ref=self.provider,
            provider="PA",
            vertragsnummer="V-123",
            laufzeit_bis=today + timedelta(days=10),
        )
        WanBeauftragung.objects.create(
            standort=self.standort,
            erstellt_von=self.user,
            titel="Upgrade",
            status=WanBeauftragung.STATUS_OFFEN,
            umsetzung_bis=today + timedelta(days=5),
        )

        call_command("generate_erinnerungen", "--days", "30")
        self.assertEqual(Erinnerung.objects.count(), 2)

    def test_generate_erinnerungen_marks_overdue(self):
        today = timezone.localdate()
        vertrag = Vertrag.objects.create(
            verwaltung=self.verwaltung,
            provider_ref=self.provider,
            provider="PA",
            vertragsnummer="V-OLD",
            laufzeit_bis=today - timedelta(days=1),
        )
        Erinnerung.objects.create(
            titel="Vertrag laeuft aus: V-OLD",
            typ=Erinnerung.TYP_VERTRAG,
            status=Erinnerung.STATUS_OFFEN,
            faellig_am=today - timedelta(days=1),
            vertrag=vertrag,
        )

        call_command("generate_erinnerungen", "--days", "0")
        reminder = Erinnerung.objects.get(vertrag=vertrag)
        self.assertEqual(reminder.status, Erinnerung.STATUS_UEBERFAELLIG)


class UserFeatureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pw")
        self.admin = User.objects.create_user(username="boss", password="pw", is_superuser=True, is_staff=True)
        self.verwaltung = Verwaltung.objects.create(name="Musterverwaltung", kuerzel="MUS")
        self.provider = Provider.objects.create(name="Provider A", kuerzel="PA")
        self.standort = Standort.objects.create(
            verwaltung=self.verwaltung,
            name="Rathaus",
            adresse_ort="Neustadt",
            adresse_strasse="Hauptstraße 1",
        )

    def test_saved_filter_create_and_apply(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("core:save_filter"),
            {"target": "erinnerung", "name": "Nur offen", "querystring": "show=offen"},
        )
        self.assertEqual(response.status_code, 302)
        filt = SavedFilter.objects.get(user=self.user)
        response = self.client.get(reverse("core:apply_filter", args=[filt.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/erinnerungen/?show=offen", response.url)

    def test_notifications_created_on_beauftragung(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("core:beauftragung_create"),
            {
                "standort": self.standort.pk,
                "titel": "Neue Leitung",
                "status": WanBeauftragung.STATUS_OFFEN,
                "prioritaet": WanBeauftragung.PRIO_NORMAL,
            },
        )
        self.assertTrue(UserNotification.objects.filter(user=self.admin).exists())

    def test_my_tasks_view(self):
        beauftragung = WanBeauftragung.objects.create(
            standort=self.standort,
            erstellt_von=self.user,
            titel="Task",
        )
        Erinnerung.objects.create(
            titel="Reminder",
            typ=Erinnerung.TYP_BEAUFTRAGUNG,
            status=Erinnerung.STATUS_OFFEN,
            faellig_am=timezone.localdate(),
            beauftragung=beauftragung,
            zugewiesen_an=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:my_tasks"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Meine Aufgaben")

    def test_approver_can_approve_and_sends_ticket_mail_with_header(self):
        beauftragung = WanBeauftragung.objects.create(
            standort=self.standort,
            erstellt_von=self.user,
            titel="Genehmigungstest",
            ticket_nummer="INC-12345",
            status=WanBeauftragung.STATUS_IN_PRUEFUNG,
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("core:beauftragung_approve", args=[beauftragung.id]),
            {"genehmigungs_notiz": "Freigabe erteilt."},
        )
        self.assertEqual(response.status_code, 302)
        beauftragung.refresh_from_db()
        self.assertTrue(beauftragung.genehmigt)
        self.assertEqual(beauftragung.genehmigt_von, self.admin)
        self.assertIsNotNone(beauftragung.ticket_gesendet_am)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["tickets@example.local"])
        self.assertEqual(mail.outbox[0].extra_headers.get("X-Ticket-Nummer"), "INC-12345")
