from django.test import TestCase

from .forms import WanLeitungForm
from .models import Provider, Standort, Tarif, Verwaltung


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

        leitung.refresh_from_db()
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
