import argparse
import os
from functools import reduce
from datetime import datetime

from opaque_keys.edx.keys import UsageKey, CourseKey
from django.core.management.base import BaseCommand, CommandError
from openedx.core.djangoapps.content.course_structures.api.v0.api import course_structure
from openedx.core.djangoapps.kursitet.management.commands.get_problem_csv_stats import Command as StatsCommand
from openedx.core.djangoapps.kursitet.csv_analyze.count import analyze_count

class Command(BaseCommand):
    help = 'call get_problem_csv_stats command for all problems in specific course unit'

    def add_arguments(self, parser):
        parser.add_argument('dir', help='directory where stats-{date-time} folder will be placed. Must to be exist')
        parser.add_argument('course', help='Course id')
        parser.add_argument('location', help='Block location. May be full locator, hash or "chapter/sequential/vertical_number" after "courseware" in url')
        parser.add_argument('--analyze', action='append', choices=['count'], default=[])

    def handle(self, *args, **options):
        key = CourseKey.from_string(options['course'])
        struct = course_structure(key)

        def _restore_block_id(id):
            lst = list(filter(lambda s: id in s, struct['blocks'].keys()))
            if len(lst) == 0:
                raise AttributeError(u'no blocks found by {} search'.format(id))
            elif len(lst) > 1:
                raise AttributeError(u'multiple blocks found by {} search. Variants: \n{}'.format(
                    id,
                    reduce(lambda a, b: '{}\n{}'.format(a, b), lst)
                ))
            return lst[0]

        loc = options['location'].split('/')
        if len(loc) == 1:
            block_id = loc[0]
        else:
            block_id = loc[1]
        block_id = _restore_block_id(block_id)
        if len(loc) == 3:
            block_id = struct['blocks'][block_id]['children'][int(loc[2])-1]
        print(u'Ready to use {} block'.format(block_id))

        stats_command = StatsCommand()

        def process_block(id, dir_name):
            block = struct['blocks'][id]
            children = block['children']
            display_name = block['display_name'].replace('/', '-')
            if len(children) > 0:
                children_dir_name = dir_name + display_name + '/'
                for child in children:
                    print(u'recursively start to process {} child in {} ({})'.format(child, display_name, id))
                    process_block(child, children_dir_name)
            elif block['type'] == 'problem':
                print(u'problem {} found. Problem id: {}'.format(display_name, id))
                if not os.path.exists(dir_name):
                    os.makedirs(dir_name)
                filename = dir_name + display_name + '.csv'
                stats_command.handle(problem=id, output=filename)
                if 'count' in options['analyze']:
                    analyze_count(filename)
            else:
                print(u'Exit: No children or problem found in {} ({})'.format(display_name, id))

        dir_name = unicode(options['dir'])
        if dir_name[-1] != '/':
            dir_name += '/'
        dir_name += datetime.now().strftime('stats-%Y-%m-%dT%H-%M-%S/')
        print(u'output dir is {}\nStart to process...'.format(dir_name))
        process_block(block_id, dir_name)
