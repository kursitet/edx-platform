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


def get_course_struct(course_name):
    locator = CourseLocator.from_string(course_name)
    course = modulestore().get_course(locator)
    if course is None:
        raise AttributeError(u'Course {id} not found!'.format(id=course_name))
    request = RequestFactory().get('/')
    return get_blocks(
        request,
        course.location,
        requested_fields=['children', 'type', 'display_name', 'block_counts'],
        block_counts=['problem']
    )


def get_block_id_from_location(location, struct):
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

    loc = location.split('/')
    if len(loc) == 1:
        block_id = loc[0]
    elif len(loc) in [2, 3]:
        block_id = loc[1]
    else:
        raise AttributeError('Bad location: expected 1, 2 or 3 values separated by "/"')
    block_id = restore_block_id(block_id)
    if len(loc) == 3:
        block_id = struct['blocks'][block_id]['children'][int(loc[2]) - 1]
    return block_id


class Block(object):
    regexp = re.compile(u'[^\\w\\-\u0403-\u044f\u0410-\u042f\u0451\u0401]', flags=re.U)  # russian alphabet

    def __new__(cls, id, struct):
        block = struct['blocks'][id]
        if (len(block.get('children', [])) > 0 and block['block_counts']['problem'] > 0) \
                or block['type'] == 'problem':
            return super(Block, cls).__new__(cls)
        return None

    def __init__(self, id, struct):
        self.block = struct['blocks'][id]
        self.id = id
        if not self.is_problem:
            self.children = [b for b in (Block(child_id, struct) for child_id in self.block['children'])
                             if b is not None]
        else:
            self.children = []

    @property
    def type(self):
        return self.block['type']

    @property
    def display_name(self):
        return self.regexp.sub('_', self.block['display_name'])

    @property
    def problem_count(self):
        return self.block['block_counts']['problem']

    @property
    def is_problem(self):
        return self.type == 'problem'


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
        struct = get_course_struct(options['course'])
        block_id = get_block_id_from_location(options['location'], struct)
        print(u'Ready to use {} block'.format(block_id))

        stats_command = StatsCommand()

        block = Block(block_id, struct)
        if block is None:
            print(u'block {} has no problems inside'.format(block_id))
            return

        errors = []

        def process(block, dir_name):
            if block.is_problem:
                print(u'Problem "{name}" found. Problem id: {id}'.format(name=block.display_name, id=block.id))
                if not os.path.exists(dir_name):
                    os.makedirs(dir_name)
                filename = dir_name + block.display_name + '.csv'
                try:
                    result = stats_command.handle(problem=block.id, output=filename)
                    if 'count' in options['analyze']:
                        analyze_count(filename)
                except UnexpectedBehavior as e:
                    errors.append(e.message)
            else:
                print (
                    u'Block "{name}" (type: {type}, id: {id}) has {problems} problems '
                    u'inside. Start to process {children} it\'s children...'
                ).format(
                    name=block.display_name, type=block.type, id=block.id,
                    problems=block.problem_count, children=len(block.children)
                )
                for child in block.children:
                    process(child, dir_name+block.display_name+'/')

        dir_name = unicode(options['dir'])
        if dir_name[-1] != '/':
            dir_name += '/'
        dir_name += datetime.now().strftime('stats-%Y-%m-%dT%H-%M-%S/')
        print(u'output dir is {}\nStart to process...'.format(dir_name))
        process(block, dir_name)

        if errors:
            print('Some errors happened:')
            for err in errors:
                print(err)
