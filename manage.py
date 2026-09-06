"""Account/data administration. Reads passwords interactively, never prints them."""
import argparse
import getpass
import json
from werkzeug.security import generate_password_hash
from app import app
from services.store import store, upsert_company

parser=argparse.ArgumentParser()
sub=parser.add_subparsers(dest='command', required=True)
user=sub.add_parser('user');user.add_argument('email')
load=sub.add_parser('import-companies');load.add_argument('path')
settings=sub.add_parser('import-settings');settings.add_argument('path')
args=parser.parse_args()
with app.app_context():
    if args.command=='user':
        password=getpass.getpass('Password: ')
        if len(password)<12:raise SystemExit('Use at least 12 characters.')
        email=args.email.strip().lower()
        hashed=generate_password_hash(password)
        store().mutate(lambda s:s['users'].update({email:{'id':email,'email':email,'password_hash':hashed}}))
        print('Account saved.')
    elif args.command=='import-companies':
        records=json.load(open(args.path,encoding='utf-8'))
        count=sum(upsert_company(row) is not None for row in records)
        print(f'{count} records imported (deduplicated).')
    elif args.command=='import-settings':
        data=json.load(open(args.path,encoding='utf-8'))
        store().mutate(lambda s:s['settings'].update(data))
        print('Draft saved.')
