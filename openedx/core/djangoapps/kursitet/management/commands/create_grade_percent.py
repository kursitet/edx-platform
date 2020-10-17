import csv
import os
import tempfile
from collections import defaultdict
from itertools import chain

from django.core.management.base import BaseCommand

from .course_unit_csv_stats import get_block_id_from_location, get_course_struct, Block
from .get_problem_csv_stats import get_modules


class Command(BaseCommand):
    help = 'calculate grade_percent csv for some course location'

    def add_arguments(self, parser):
        parser.add_argument(
            'output',
            help='where csv file will be placed'
        )
        parser.add_argument('course', help='Course id')
        parser.add_argument(
            'location',
            help='Block location. May be full locator, hash or '
                 '"chapter/sequential/vertical_number" after "courseware" in url'
        )

    def handle(self, *args, **options):
        struct = get_course_struct(options['course'])
        block_id = get_block_id_from_location(options['location'], struct)
        print u'ready to use {} block'.format(block_id)
        block = Block(block_id, struct)
        if block is None:
            print u'No problems in {}'.format(block_id)

        def write_queue_to_blocks(block):
            if block.is_problem:
                queue, _ = get_modules(block.id)
                block.queue = queue
            else:
                for child in block.children:
                    write_queue_to_blocks(child)

        def get_nested_queues(block):
            if block.is_problem:
                return [block.queue]
            return chain.from_iterable(get_nested_queues(child) for child in block.children)

        write_queue_to_blocks(block)
        if block.is_problem:
            # dirty hack
            block.children = [block]
        accum = defaultdict(lambda: defaultdict(lambda: dict(grade=0, max_grade=0)))
        for child in block.children:
            child_queues = get_nested_queues(child)
            for queue in child_queues:
                for user_dict, _ in queue:
                    if user_dict['attempts'] > 0:
                        d = accum[user_dict['username']][child.id]
                        d['grade'] += user_dict['grade']
                        # sometimes max_grade is '', but i think in attempts > 0 it is not real
                        d['max_grade'] += user_dict['max_grade']

        with tempfile.NamedTemporaryFile(
                'w', dir=os.path.dirname(options['output']),
                delete=False
        ) as file:
            writer = csv.writer(file, quoting=csv.QUOTE_ALL)
            writer.writerow(['username'] + [child.display_name.encode('utf-8') for child in block.children])
            for username, cols_dict in accum.items():
                writer.writerow([username] + [
                    str(float(grade)/maxi) if maxi != 0 else '-' for grade, maxi in (
                        (num_dict['grade'], num_dict['max_grade']) for num_dict in (
                            cols_dict[child.id] for child in block.children)
                    )
                ])
            actual_filename = file.name
        os.rename(actual_filename, options['output'])
        print u'grade_percent successfully created! Look in {}'.format(options['output'])
