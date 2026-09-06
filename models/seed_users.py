"""Legacy SQL account seeding was replaced by persistent, hashed accounts."""

def seed_initial_users():
    raise RuntimeError('Use python manage.py user <email> to provision an account.')
