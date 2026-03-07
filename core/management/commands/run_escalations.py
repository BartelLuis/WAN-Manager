from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Erinnerung, LeitungsStoerung, UserNotification, WanBeauftragung


class Command(BaseCommand):
    help = "Eskalationen fuer ueberfaellige Aufgaben und SLA-Verletzungen erzeugen."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts speichern.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = timezone.now()
        today = timezone.localdate()

        overdue_reminders = Erinnerung.objects.filter(
            status=Erinnerung.STATUS_OFFEN,
            faellig_am__lt=today,
        ).select_related("zugewiesen_an")

        stalled_orders = WanBeauftragung.objects.filter(
            status__in=[WanBeauftragung.STATUS_OFFEN, WanBeauftragung.STATUS_IN_PRUEFUNG],
            umsetzung_bis__isnull=False,
            umsetzung_bis__lt=today,
        )

        sla_breaches = LeitungsStoerung.objects.filter(
            status__in=[LeitungsStoerung.STATUS_OFFEN, LeitungsStoerung.STATUS_IN_BEARBEITUNG],
            erwartet_behebung_bis__isnull=False,
            erwartet_behebung_bis__lt=now,
        )

        created = 0
        for reminder in overdue_reminders:
            if reminder.zugewiesen_an_id and not dry_run:
                UserNotification.objects.create(
                    user=reminder.zugewiesen_an,
                    titel=f"Eskalation Erinnerung: {reminder.titel}",
                    nachricht=f"Faellig seit {reminder.faellig_am:%d.%m.%Y}",
                    link="/erinnerungen/",
                )
                created += 1

        for beauftragung in stalled_orders:
            if not dry_run and beauftragung.erstellt_von_id:
                UserNotification.objects.create(
                    user=beauftragung.erstellt_von,
                    titel=f"Eskalation Beauftragung: {beauftragung.titel}",
                    nachricht="Umsetzungstermin ist ueberfaellig.",
                    link=f"/beauftragungen/{beauftragung.pk}/",
                )
                created += 1

        ops_users = list(UserNotification.objects.none())
        if not dry_run:
            from django.contrib.auth.models import User
            ops_users = User.objects.filter(is_superuser=True)

        for stoerung in sla_breaches:
            if not dry_run:
                for user in ops_users:
                    UserNotification.objects.create(
                        user=user,
                        titel=f"SLA-Verletzung: {stoerung.titel}",
                        nachricht=f"Leitung {stoerung.wanleitung}",
                        link=f"/stoerungen/{stoerung.pk}/",
                    )
                    created += 1

        mode = "DRY-RUN" if dry_run else "WRITE"
        self.stdout.write(self.style.SUCCESS(
            f"[{mode}] Eskalationen: Erinnerungen={overdue_reminders.count()} Beauftragungen={stalled_orders.count()} SLA={sla_breaches.count()} Notifications={created}"
        ))
