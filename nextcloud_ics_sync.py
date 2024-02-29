#!/usr/bin/env python3
import configparser
import logging
import requests
import traceback
from icalendar.cal import Calendar
import urllib.parse

log_option = {
    'format': '[%(asctime)s] [%(levelname)s] %(message)s',
    'level': logging.INFO
}
logging.basicConfig(**log_option)
logging.getLogger("requests").setLevel(logging.WARNING)

CALDAVURL = '%sremote.php/dav/calendars/%s/%s'


def do_import(username, password, calendar, server, ics_url, \
              ics_username, ics_password):
    logging.info('  Working with calendar %s...', calendar)
    base_url = CALDAVURL % (server, username, calendar)

    target_fetch_url = f'{base_url}?export'
    encoded_password = urllib.parse.quote(password, safe='')
    r = requests.get(target_fetch_url, auth=(username, encoded_password))
    r.raise_for_status()
    try:
        target_cal = Calendar.from_ical(r.text)
    except ValueError as e:
        logging.error('    Warning: Could not parse iCal (%s)', target_fetch_url)
        logging.error(e)
        return

    existing_uids = [bytes.decode(e['UID'].to_ical()).replace('\'', '')\
                     .replace('/', 'slash') for e in target_cal.walk('VEVENT')]

    encoded_ics_password = urllib.parse.quote(ics_password, safe='')
    sourceRequest = requests.get(ics_url, auth=(ics_username, encoded_ics_password))
    sourceRequest.encoding = 'utf-8'
    sourceContent = sourceRequest.text
    c = Calendar.from_ical(sourceContent)

    distant_uids = [bytes.decode(e['UID'].to_ical()).replace('\'', '')\
                    .replace('/', 'slash') for e in c.walk('VEVENT')]

    imported_uids = []
    for e in c.walk('VEVENT'):
        uid = bytes.decode(e['UID'].to_ical()).replace('\'', '').replace('/', 'slash')
        name = bytes.decode(e['SUMMARY'].to_ical())
        if uid not in existing_uids:
            cal = Calendar()
            cal.add_component(e)
            r = requests.put(
                f'{base_url}/{uid}.ics',
                data=cal.to_ical(),
                auth=(username, encoded_password),
                headers={'content-type': 'text/calendar; charset=UTF-8'}
            )
            if r.status_code == 500 and \
                r'Sabre\VObject\Recur\NoInstancesException' in r.text:
                logging.warning('   No valid instances: %s (%s)', uid, name)
            elif r.status_code in (201, 204):
                logging.info('   Imported: %s (%s)', uid, name)
                imported_uids.append(uid)
            else:
                r.raise_for_status()

    for euid in existing_uids:
        if euid not in distant_uids:
            r = requests.delete(
                f'{base_url}/{uid}.ics', auth=(username, encoded_password))
        if r.status_code == 204:
            logging.info('Deleted %s', euid)
        elif r.status_code == 404:
            pass
        else:
            r.raise_for_status()
    logging.info('  Done.')


if __name__ == '__main__':
    logging.info('Initializing script...')
    Config = configparser.RawConfigParser()
    Config.read('nextcloud_ics_sync.ini')
    logging.info('Done.')
    logging.info('Importing calendars...')
    for key in Config.sections():
        logging.info(' Working on section %s', key)
        try:
            do_import(
                Config.get(key, 'username'),
                Config.get(key, 'password'),
                Config.get(key, 'calendar'),
                Config.get(key, 'server'),
                Config.get(key, 'ics_url'),
                Config.get(key, 'ics_username'),
                Config.get(key, 'ics_password')
            )
        except Exception as e:
            logging.error(traceback.print_exc())
        logging.info(' Done.')
    logging.info('Done.')
