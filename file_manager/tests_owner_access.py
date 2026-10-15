import uuid
from django.contrib.auth import get_user_model
from django.test import TestCase
from file_manager.models import ManagedFile, ManagedFileBusinessRelation
from file_manager.business_access import user_can_access_business
from file_manager.business_relations import files_for_business, files_for_businesses


class OwnerAttachmentTests(TestCase):
    def test_same_business_id_does_not_expose_another_users_files(self):
        User = get_user_model()
        owner = User.objects.create_user(username='owner')
        other = User.objects.create_user(username='other')
        for user in [owner, other]:
            file = ManagedFile.objects.create(user=user, file_uuid=uuid.uuid4(), original_name='photo.jpg')
            ManagedFileBusinessRelation.objects.create(user=user, file=file, business_type='diary', business_id='shared-id')
        self.assertTrue(user_can_access_business(owner, 'diary', 'shared-id'))
        self.assertEqual(list(files_for_business(owner, 'diary', 'shared-id').values_list('user_id', flat=True)), [owner.id])
        self.assertEqual(list(files_for_businesses(owner, [('diary', ['shared-id'])]).values_list('user_id', flat=True)), [owner.id])
        owner.managed_files.update(is_deleted=True)
        self.assertFalse(user_can_access_business(owner, 'diary', 'shared-id'))
