import os
import re
from datetime import datetime

from opaque_keys.edx.locator import CourseLocator
from django.core.management.base import BaseCommand, CommandError
from django.test.client import RequestFactory
from xmodule.modulestore.django import modulestore
from course_api.blocks.api import get_blocks

from openedx.core.djangoapps.kursitet.csv_analyze.count import analyze_count
from .get_problem_csv_stats import UnexpectedBehavior
from .get_problem_csv_stats import Command as StatsCommand


class Command(BaseCommand):
    help = 'call get_problem_csv_stats command for all problems in specific course unit'

    def add_arguments(self, parser):
        parser.add_argument(
            'dir',
            help='directory where stats-{date-time} folder will be placed. Must to be exist'
        )
        parser.add_argument('course', help='Course id')
        parser.add_argument(
            'location',
            help='Block location. May be full locator, hash or '
                 '"chapter/sequential/vertical_number" after "courseware" in url'
        )
        parser.add_argument('--analyze', action='append', choices=['count'], default=[])

    def handle(self, *args, **options):
        locator = CourseLocator.from_string(options['course'])
        course = modulestore().get_course(locator)
        if course is None:
            raise AttributeError(u'Course {id} not found!'.format(id=options['course']))
        request = RequestFactory().get('/')
        struct = get_blocks(
            request,
            course.location,
            requested_fields=['children', 'type', 'display_name', 'block_counts'],
            block_counts=['problem']
        )

        def restore_block_id(id):
            lst = [s for s in struct['blocks'].keys() if id in s]
            if len(lst) == 0:
                raise AttributeError(u'no blocks found by {} search'.format(id))
            elif len(lst) > 1:
                raise AttributeError(
                    u'multiple blocks found by {} search. Variants: \n{}'.format(
                        id,
                        '\n'.join(lst)
                    ))
            return lst[0]

        loc = options['location'].split('/')
        if len(loc) == 1:
            block_id = loc[0]
        elif len(loc) in [2, 3]:
            block_id = loc[1]
        else:
            raise AttributeError('Bad location: expected 1, 2 or 3 values separated by "/"')
        block_id = restore_block_id(block_id)
        if len(loc) == 3:
            block_id = struct['blocks'][block_id]['children'][int(loc[2])-1]
        print(u'Ready to use {} block'.format(block_id))

        stats_command = StatsCommand()

        regexp = re.compile(u'[^\\w\\-\u0403-\u044f\u0410-\u042f\u0451\u0401]', flags=re.U)  # russian alphabet
        errors = []
        def process_block(id, dir_name):
            block = struct['blocks'][id]
            children = block.get('children', [])
            block_type = block['type']
            display_name = regexp.sub('_', block['display_name'])

            if len(children) > 0:
                problem_count = block['block_counts']['problem']
                if problem_count > 0:
                    print (
                        u'Block "{name}" (type: {type}, id: {id}) has {problems} problems '
                        u'inside. Start to process {children} it\'s children...'
                    ).format(
                        name=display_name, type=block_type, id=id,
                        problems=problem_count, children=len(children)
                    )
                    for child in children:
                        process_block(child, dir_name + display_name + '/')
                else:
                    print (
                        u'Block "{name}" (id: {id}) has some children '
                        u'but no problems. I will not process them'
                    ).format(name=display_name, id=id)
            elif block_type == 'problem':
                print(u'Problem "{name}" found. Problem id: {id}'.format(name=display_name, id=id))
                if not os.path.exists(dir_name):
                    os.makedirs(dir_name)
                filename = dir_name + display_name + '.csv'
                try:
                    stats_command.handle(problem=id, output=filename)
                except UnexpectedBehavior as e:
                    errors.append(e.message)
                if 'count' in options['analyze']:
                    analyze_count(filename)
            else:
                print (
                    u'Block "{name}" (type: {type}, id: {id}) has no children or problems'
                ).format(name=display_name, type=block_type, id=id)

        dir_name = unicode(options['dir'])
        if dir_name[-1] != '/':
            dir_name += '/'
        dir_name += datetime.now().strftime('stats-%Y-%m-%dT%H-%M-%S/')
        print(u'output dir is {}\nStart to process...'.format(dir_name))
        process_block(block_id, dir_name)

        if errors:
            print('Some errors happened:')
            for err in errors:
                print(err)
