from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Seed admin users with superuser permissions'

    def handle(self, *args, **options):
        users_data = [
            {
                'username': 'admin1',
                'email': 'admin1@example.com',
                'password': 'admin123',
                'first_name': 'Admin',
                'last_name': 'One'
            },
            {
                'username': 'admin2',
                'email': 'admin2@example.com',
                'password': 'admin123',
                'first_name': 'Admin',
                'last_name': 'Two'
            }
        ]
        
        users_created = 0
        users_skipped = 0
        
        self.stdout.write(self.style.WARNING('Creating admin users...'))
        
        for user_data in users_data:
            username = user_data['username']
            
            if User.objects.filter(username=username).exists():
                users_skipped += 1
                self.stdout.write(
                    self.style.WARNING(f'User {username} already exists, skipping...')
                )
                continue
            
            User.objects.create_superuser(
                username=user_data['username'],
                email=user_data['email'],
                password=user_data['password'],
                first_name=user_data['first_name'],
                last_name=user_data['last_name']
            )
            
            users_created += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f'Created superuser: {username} (email: {user_data["email"]}, password: {user_data["password"]})'
                )
            )
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*50))
        self.stdout.write(self.style.SUCCESS(f'Users created: {users_created}'))
        self.stdout.write(self.style.SUCCESS(f'Users skipped (already exist): {users_skipped}'))
        self.stdout.write(self.style.SUCCESS('='*50))
