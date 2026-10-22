from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .models import Attachment,HelpImage,GarbageObject
@receiver(pre_delete,sender=Attachment)
@receiver(pre_delete,sender=HelpImage)
def retain_object_cleanup(sender,instance,**kwargs):
    # Store a durable tombstone before cascading account/data deletion removes the object's metadata.
    GarbageObject.objects.get_or_create(key=instance.key)
