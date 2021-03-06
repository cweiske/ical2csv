import argparse
import copy
from datetime import date, datetime, time, timedelta
import itertools
import sys

from dateutil.relativedelta import relativedelta
from icalendar import Calendar
import pytz

DELTAS = {
    'SECONDLY': timedelta(seconds=1),
    'MINUTELY': timedelta(minutes=1),
    'HOURLY': timedelta(hours=1),
    'WEEKLY': timedelta(weeks=1),
    'MONTHLY': relativedelta(months=1),
}

WEEKDAYS = {
    'MO': 0,
    'TU': 1,
    'WE': 2,
    'TH': 3,
    'FR': 4,
    'SA': 5,
    'SU': 6
}

def process(ics_string, end_date, start_date=None, include_full_day=False):
    cal = Calendar.from_ical(ics_string)

    heading = 'UID,CREATED,LAST-MODIFIED,DTSTART,DTEND,SUMMARY,LOCATION'
    yield heading

    keys = heading.split(',')

    for item in cal.walk():
        if item.name != 'VEVENT':
            continue

        try:
            item_start = item['DTSTART'].dt
            item_end = item['DTEND'].dt
        except KeyError as e:
            sys.stderr.write("KeyError on item: %s\n\t%s\n\n" % (item, e))
            continue

        if (isinstance(item_start, date) and not isinstance(item_start, datetime)
            and not include_full_day):
            continue

        if not isinstance(item_start, datetime):
            item_start = datetime.combine(item_start, time(0, 0, 0, 0, start_date.tzinfo))
        if not isinstance(item_end, datetime):
            item_end = datetime.combine(item_end, time(23, 59, 59, 0, end_date.tzinfo))

        if (start_date is not None and start_date > item_start) or end_date < item_end:
            continue

        item['SUMMARY'] = item['SUMMARY'].replace(',', ';')
        if item.has_key('LOCATION'):
            item['LOCATION'] = item['LOCATION'].replace(',', ';')
        else:
            item['LOCATION'] = ''

        yield ','.join(str(item[key].dt)
                       if hasattr(item[key], 'dt')
                       else item[key]
                       for key in keys)

        # Handle recurrence rules
        if 'RRULE' in item:
            rrule = item['RRULE']
            delta = DELTAS[rrule['FREQ'][0]]
            recur_item = {key: copy.copy(item[key].dt)
                          if hasattr(item[key], 'dt')
                          else item[key]
                          for key in keys}

            # Exceptions
            exception_dates = set()
            if 'EXDATE' in item:
                exdate_data = item['EXDATE']
                if not isinstance(exdate_data, list):
                    # Sometimes this comes nested and sometimes not :(
                    exdate_data = [item['EXDATE']]

                exception_dates = [[dt_obj.dt for dt_obj in exdate_nested.dts]
                                   for exdate_nested in exdate_data]
                exception_dates = set(itertools.chain(*exception_dates))

            rooted_deltas = [timedelta(days=0)]
            if 'BYDAY' in rrule:
                first_day = WEEKDAYS[rrule['BYDAY'][0]]
                rooted_deltas.extend([timedelta(days=WEEKDAYS[day] - first_day)
                                      for day in rrule['BYDAY'][1:]])

            if 'UNTIL' in rrule:
                until = rrule['UNTIL'][0]

                while recur_item['DTSTART'] <= until:
                    recur_item['DTSTART'] += delta
                    recur_item['DTEND'] += delta

                    unrooted_item = copy.copy(recur_item)
                    for rooted_delta in rooted_deltas:
                        unrooted_item['DTSTART'] += rooted_delta
                        unrooted_item['DTEND'] += rooted_delta

                        if unrooted_item['DTSTART'] in exception_dates:
                            continue

                        yield ','.join(str(unrooted_item[key])
                                       for key in keys)

            elif 'COUNT' in rrule:
                count = rrule['COUNT']
                count = count[0] if isinstance(count, list) else count
                for _ in range(count):
                    recur_item['DTSTART'] += delta
                    recur_item['DTEND'] += delta

                    unrooted_item = copy.copy(recur_item)
                    for rooted_delta in rooted_deltas:
                        unrooted_item['DTSTART'] += rooted_delta
                        unrooted_item['DTEND'] += rooted_delta

                        if unrooted_item['DTSTART'] in exception_dates:
                            continue

                        yield ','.join(str(unrooted_item[key])
                                       for key in keys)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert an ICS file to CSV.')
    parser.add_argument('file', type=argparse.FileType('r'))
    parser.add_argument('--start-date', required=False)
    parser.add_argument('--end-date',
                        default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--timezone', default='America/Los_Angeles')
    parser.add_argument('--include-full-day', type=bool, default=False)
    args = parser.parse_args()

    data = args.file.read()
    args.file.close()

    timezone = pytz.timezone(args.timezone)
    format = '%Y-%m-%d'
    start_date = timezone.localize(
        datetime.strptime(args.start_date or '1970-01-01', format))
    end_date = timezone.localize(
        datetime.strptime(args.end_date or '3000-01-01', format))

    for csv_line in process(data, end_date, start_date,
                         args.include_full_day):
        print(csv_line)
