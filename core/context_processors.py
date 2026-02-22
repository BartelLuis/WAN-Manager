from .models import UserNotification


def notification_context(request):
    if not request.user.is_authenticated:
        return {"unread_notifications": 0}
    return {
        "unread_notifications": UserNotification.objects.filter(user=request.user, gelesen=False).count()
    }
